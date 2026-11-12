import io
import re
import zipfile
from typing import Dict, List, Any
from xml.etree import ElementTree

from sklearn.metrics.pairwise import cosine_similarity

from ml.model import JOB_PROFILES, vectorizer

TECH_SKILLS = [
    "python", "javascript", "typescript", "java", "c++", "cplusplus", "cpp", "c#", "csharp",
    "go", "golang", "rust", "php", "ruby", "kotlin", "swift", "dart", "r", "scala",
    "sql", "html", "css", "bash", "shell", "powershell", "matlab",
    "react", "react.js", "reactjs", "angular", "vue", "vue.js", "next.js", "nextjs",
    "node", "node.js", "nodejs", "express", "express.js", "django", "flask", "fastapi",
    "spring", "spring boot", "asp.net", "dotnet", ".net", "laravel", "symfony",
    "flutter", "react native", "pandas", "numpy", "scikit-learn", "sklearn", "tensorflow",
    "pytorch", "keras", "opencv", "matplotlib", "seaborn", "tailwind", "bootstrap", "gsap",
    "mysql", "postgresql", "postgres", "mongodb", "sqlite", "redis", "cassandra",
    "elasticsearch", "oracle", "dynamodb", "firebase", "spark", "hadoop", "airflow", "dbt",
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "ci/cd", "ci cd", "git", "github", "gitlab", "linux", "nginx", "jenkins",
    "ansible", "helm", "devops",
    "selenium", "playwright", "cypress", "pytest", "junit", "jest", "postman", "jira",
    "rest api", "rest", "restful", "graphql", "microservices", "system design",
    "machine learning", "deep learning", "llm", "nlp", "computer vision", "statistics",
    "data analysis", "data visualization", "cybersecurity", "figma", "ui/ux", "agile", "scrum"
]


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\bc\s*\+\s*\+", "cplusplus", text)
    text = re.sub(r"\bc\s*#", "csharp", text)
    text = re.sub(r"\.net\b", "dotnet", text)
    text = re.sub(r"\bnode\.?js\b", "nodejs", text)
    text = re.sub(r"\breact\.?js\b", "react", text)
    text = re.sub(r"\bvue\.?js\b", "vue", text)
    text = re.sub(r"\bnext\.?js\b", "nextjs", text)
    text = re.sub(r"\bci\s*/\s*cd\b", "ci/cd", text)
    return text


ALLOWED_RESUME_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_RESUME_PAGES = 2
ESTIMATED_WORDS_PER_PAGE = 500


def _validate_resume_page_count(page_count: int, estimated: bool = False) -> None:
    if page_count > MAX_RESUME_PAGES:
        page_description = "is estimated at" if estimated else "has"
        raise ValueError(
            f"Resume must be no more than {MAX_RESUME_PAGES} pages; "
            f"the uploaded file {page_description} {page_count} pages."
        )


def _estimated_text_pages(text: str) -> int:
    words = len(re.findall(r"\b\w+\b", text))
    estimated_pages = (words + ESTIMATED_WORDS_PER_PAGE - 1) // ESTIMATED_WORDS_PER_PAGE
    explicit_pages = text.count("\f") + 1
    return max(1, estimated_pages, explicit_pages)


def _docx_page_count(file_storage, text: str) -> int:
    page_count = _estimated_text_pages(text)
    file_storage.seek(0)
    document_xml = file_storage.read()
    file_storage.seek(0)
    with zipfile.ZipFile(io.BytesIO(document_xml)) as archive:
        if "docProps/app.xml" in archive.namelist():
            properties = ElementTree.fromstring(archive.read("docProps/app.xml"))
            pages = properties.find("{*}Pages")
            if pages is not None and pages.text and pages.text.isdigit():
                page_count = max(page_count, int(pages.text))

        if "word/document.xml" in archive.namelist():
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            page_breaks = document.findall(".//w:br[@w:type='page']", namespaces)
            page_breaks += document.findall(".//w:pageBreakBefore", namespaces)
            page_count = max(page_count, len(page_breaks) + 1)

    return page_count


def extract_text_from_file(file_storage, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: .{ext or 'unknown'}. Please upload a PDF, DOCX, or TXT resume file."
        )

    text = ""

    if ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_storage)
            _validate_resume_page_count(len(reader.pages))
            pages_text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            text = "\n".join(pages_text)
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Could not parse PDF file: {str(e)}")

    elif ext == "docx":
        try:
            import docx
            doc = docx.Document(file_storage)
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            paragraphs.append(cell.text)
            text = "\n".join(paragraphs)
            _validate_resume_page_count(
                _docx_page_count(file_storage, text),
                estimated=True,
            )
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Could not parse Word document: {str(e)}")

    elif ext == "txt":
        try:
            content = file_storage.read()
            if isinstance(content, bytes):
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    text = content.decode("latin-1", errors="replace")
            else:
                text = str(content)
            _validate_resume_page_count(
                _estimated_text_pages(text),
                estimated=True,
            )
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Could not read text file: {str(e)}")
    return text.strip()


def extract_contact_info(text: str) -> Dict[str, Any]:
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    emails = list(set(re.findall(email_pattern, text)))

    phone_pattern = r"(?:(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\b\d{10}\b))"
    phones = list(set(re.findall(phone_pattern, text)))

    linkedin = bool(re.search(r"linkedin\.com/in/[\w-]+", text, re.IGNORECASE))
    github = bool(re.search(r"github\.com/[\w-]+", text, re.IGNORECASE))
    portfolio = bool(re.search(r"(portfolio|personal website|github\.io|vercel\.app)", text, re.IGNORECASE))

    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "has_linkedin": linkedin,
        "has_github": github,
        "has_portfolio": portfolio,
    }


def detect_sections(text: str) -> List[str]:
    sections = []
    text_lower = text.lower()

    checks = {
        "Experience / Work History": [r"\bexperience\b", r"\bwork history\b", r"\bemployment\b", r"\bwork experience\b"],
        "Education": [r"\beducation\b", r"\bacademics\b", r"\buniversity\b", r"\bdegree\b", r"\bcollege\b"],
        "Projects": [r"\bprojects\b", r"\bpersonal projects\b", r"\bkey projects\b", r"\baccomplishments\b"],
        "Skills": [r"\bskills\b", r"\btechnical skills\b", r"\btechnologies\b", r"\bcore competencies\b"],
        "Certifications": [r"\bcertifications\b", r"\bcertificates\b", r"\blicenses\b", r"\bcredentials\b"],
    }

    for section_name, patterns in checks.items():
        if any(re.search(p, text_lower) for p in patterns):
            sections.append(section_name)

    return sections


def format_resume_for_ats(text: str) -> str:
    heading_patterns = {
        "EXPERIENCE": r"^(?:work\s+)?experience|work\s+history|employment(?:\s+history)?$",
        "EDUCATION": r"^(?:education|academic(?:s)?|academic\s+background)$",
        "PROJECTS": r"^(?:projects?|personal\s+projects?|key\s+projects?)$",
        "SKILLS": r"^(?:skills|technical\s+skills|core\s+competencies|technologies)$",
        "CERTIFICATIONS": r"^(?:certifications?|certificates?|licenses|credentials)$",
        "SUMMARY": r"^(?:professional\s+)?summary|profile|objective$",
    }
    heading_patterns = {
        name: re.compile(pattern, re.IGNORECASE)
        for name, pattern in heading_patterns.items()
    }
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[•▪●◦‣]", "- ", text)
    text = re.sub(r"[ \t]+", " ", text)

    formatted_lines = []
    previous_blank = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            if formatted_lines and not previous_blank:
                formatted_lines.append("")
            previous_blank = True
            continue

        heading = next(
            (name for name, pattern in heading_patterns.items() if pattern.fullmatch(line.rstrip(":"))),
            None,
        )
        if heading:
            line = heading
        elif line.startswith(("-", "*")):
            line = "- " + line.lstrip("-* ").strip()

        formatted_lines.append(line)
        previous_blank = False

    return "\n".join(formatted_lines).strip()


def extract_skills_from_text(text: str) -> List[str]:
    normalized = normalize_text(text)
    found_skills = set()

    for skill in TECH_SKILLS:
        norm_skill = normalize_text(skill)
        pattern = r"(?:^|\W)" + re.escape(norm_skill) + r"(?:$|\W)"
        if re.search(pattern, normalized):
            display_name = skill.replace("cplusplus", "C++").replace("csharp", "C#").replace("dotnet", ".NET")
            found_skills.add(display_name.title() if len(display_name) > 3 else display_name.upper())

    return sorted(list(found_skills))


def get_role_profile(role_name: str) -> Dict[str, Any]:
    role_norm = role_name.lower().strip()

    for profile in JOB_PROFILES:
        if profile["title"].lower() == role_norm or role_norm in profile["title"].lower() or profile["title"].lower() in role_norm:
            return profile

    best_match = None
    best_overlap = 0
    role_tokens = set(role_norm.split())
    for profile in JOB_PROFILES:
        profile_tokens = set(profile["title"].lower().split())
        overlap = len(role_tokens.intersection(profile_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = profile

    if best_match and best_overlap > 0:
        return best_match

    return {
        "title": role_name.title(),
        "skills": role_norm,
    }


def get_resume_role_recommendations(resume_text: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not resume_text or len(resume_text.strip()) < 20:
        return []

    resume_skills = extract_skills_from_text(resume_text)
    resume_skill_set = {skill.lower() for skill in resume_skills}
    normalized_resume = normalize_text(resume_text)
    user_vec = vectorizer.transform([normalized_resume])

    scored_profiles = []
    for profile in JOB_PROFILES:
        profile_skills = extract_skills_from_text(profile["skills"])
        profile_skill_set = {skill.lower() for skill in profile_skills}
        overlap = len(resume_skill_set & profile_skill_set)
        overlap_ratio = overlap / max(len(profile_skill_set), 1)
        matched_skills = [
            skill for skill in profile_skills if skill.lower() in resume_skill_set
        ]

        profile_vec = vectorizer.transform([normalize_text(profile["skills"])])
        vector_sim = float(cosine_similarity(user_vec, profile_vec)[0][0])
        score = round((overlap_ratio * 0.7 + vector_sim * 0.3) * 100)

        if matched_skills:
            scored_profiles.append({
                "title": profile["title"],
                "match": max(10, min(99, score)),
                "matched_skills": matched_skills,
            })

    scored_profiles.sort(key=lambda item: item["match"], reverse=True)
    seen = set()
    recommended_roles = []
    for role in scored_profiles:
        if role["title"] in seen:
            continue
        seen.add(role["title"])
        recommended_roles.append(role)
        if len(recommended_roles) >= limit:
            break

    return recommended_roles


def validate_resume_content(resume_text: str) -> None:
    if not resume_text or len(resume_text.strip()) < 20:
        raise ValueError("Resume content is too short or empty. Please provide readable resume text.")

    section_headings = {
        "summary", "professional summary", "profile", "profile summary", "objective",
        "experience", "professional experience", "work experience", "work history",
        "employment", "employment history", "career history",
        "education", "academic background", "skills", "technical skills",
        "technical expertise", "core competencies", "projects", "key projects",
        "certifications", "licenses",
    }
    headings_found = {
        line.strip().rstrip(":").lower()
        for line in resume_text.splitlines()
        if line.strip().rstrip(":").lower() in section_headings
    }
    skills_found = extract_skills_from_text(resume_text)
    contact_info = extract_contact_info(resume_text)
    has_contact = bool(
        contact_info["email"]
        or contact_info["phone"]
        or contact_info["has_linkedin"]
        or contact_info["has_github"]
    )
    has_bullets = bool(re.search(r"(?m)^\s*[-*•▪●◦‣]\s+\S", resume_text))
    has_dates = bool(re.search(r"\b(?:19|20)\d{2}\b", resume_text))

    has_resume_structure = (
        len(headings_found) >= 2
        or (
            len(headings_found) >= 1
            and (has_contact or has_bullets or has_dates)
        )
        or (has_contact and len(skills_found) >= 2 and (has_bullets or has_dates))
    )
    if not has_resume_structure:
        raise ValueError(
            "This content does not look like a resume. Include resume sections such as "
            "Experience, Education, Skills, or Projects, or provide contact details and "
            "work history."
        )


def analyze_resume_for_role(resume_text: str, target_role: str) -> Dict[str, Any]:
    validate_resume_content(resume_text)

    recommended_roles = get_resume_role_recommendations(resume_text, limit=5)
    target_role = target_role.strip()
    if not target_role:
        if not recommended_roles:
            raise ValueError(
                "Could not identify a matching role from this resume. Add relevant skills "
                "or choose a target role and try again."
            )
        target_role = recommended_roles[0]["title"]

    profile = get_role_profile(target_role)
    role_skills_raw = profile["skills"].split()

    role_required_skills = []
    for s in role_skills_raw:
        s_norm = s.replace("cplusplus", "C++").replace("csharp", "C#").replace("dotnet", ".NET")
        role_required_skills.append(s_norm.title() if len(s_norm) > 3 else s_norm.upper())

    resume_skills = extract_skills_from_text(resume_text)
    resume_skills_lower = [s.lower() for s in resume_skills]

    matched_skills = []
    missing_skills = []
    for r_skill in role_required_skills:
        if r_skill.lower() in resume_skills_lower or normalize_text(r_skill) in normalize_text(resume_text):
            matched_skills.append(r_skill)
        else:
            missing_skills.append(r_skill)

    extra_skills = [s for s in resume_skills if s not in matched_skills]

    total_role_skills = len(role_required_skills)
    skill_coverage = (len(matched_skills) / total_role_skills) if total_role_skills > 0 else 0.5

    norm_resume = normalize_text(resume_text)
    user_vec = vectorizer.transform([norm_resume])
    role_corpus_vec = vectorizer.transform([normalize_text(profile["skills"])])
    vector_sim = float(cosine_similarity(user_vec, role_corpus_vec)[0][0])

    raw_score = (skill_coverage * 0.65) + (vector_sim * 0.35)
    match_score = min(100, max(10, round(raw_score * 100)))

    words = re.findall(r"\b\w+\b", resume_text)
    word_count = len(words)

    contact_info = extract_contact_info(resume_text)
    sections = detect_sections(resume_text)

    has_email = bool(contact_info["email"])
    has_phone = bool(contact_info["phone"])
    has_profile = any(
        contact_info[key] for key in ("has_linkedin", "has_github", "has_portfolio")
    )
    section_names = {section.split(" / ")[0] for section in sections}
    bullet_count = len(re.findall(r"(?m)^\s*(?:[-*•▪●◦‣])\s+\S", resume_text))
    has_metrics = bool(re.search(
        r"(\d+%\s*|\$\d+|\d+\+?\s*(users|clients|projects|features|ms|x|increase|reduction|improvement))",
        resume_text,
        re.IGNORECASE,
    ))

    ats_checks = [
        {
            "name": "Contact details",
            "score": (10 if has_email else 0) + (6 if has_phone else 0) + (4 if has_profile else 0),
            "max_score": 20,
            "detail": "Email, phone, and professional profile links are easy to find.",
        },
        {
            "name": "Standard section headings",
            "score": sum(
                10 for section in ("Experience", "Education", "Projects", "Skills")
                if section in section_names
            ),
            "max_score": 40,
            "detail": "Use clear headings for experience, education, projects, and skills.",
        },
        {
            "name": "Bullet-point structure",
            "score": 10 if bullet_count >= 2 else 0,
            "max_score": 10,
            "detail": "Use simple text bullets for responsibilities and achievements.",
        },
        {
            "name": "Measurable achievements",
            "score": 10 if has_metrics else 0,
            "max_score": 10,
            "detail": "Include truthful numbers or outcomes where you can support them.",
        },
        {
            "name": "Resume length",
            "score": 20 if 350 <= word_count <= 800 else 12 if 200 <= word_count <= 1000 else 5,
            "max_score": 20,
            "detail": "Keep resume content focused; this check uses word count as a rough guide.",
        },
    ]
    ats_score = sum(check["score"] for check in ats_checks)

    ats_tips = []

    if missing_skills:
        tips_skills = ", ".join(missing_skills[:5])
        ats_tips.append({
            "type": "keyword",
            "category": "High Priority",
            "title": "Add Key Target Role Skills",
            "message": f"ATS filters check for specific role keywords. Consider highlighting experience with: {tips_skills}.",
        })

    has_metrics = bool(re.search(r"(\d+%\s*|\$\d+|\d+\+?\s*(users|clients|projects|features|ms|x|increase|reduction|improvement))", resume_text, re.IGNORECASE))
    if not has_metrics:
        ats_tips.append({
            "type": "content",
            "category": "Impact",
            "title": "Include Quantifiable Achievements",
            "message": "Resumes with measurable results (e.g., 'Improved load time by 35%', 'Managed 50K+ requests/sec') score significantly higher with hiring managers.",
        })
    else:
        ats_tips.append({
            "type": "positive",
            "category": "Impact",
            "title": "Great Quantifiable Evidence Found",
            "message": "Your resume includes numerical achievements and metrics, which recruiters love to see!",
        })

    missing_sections = [s for s in ["Experience / Work History", "Projects", "Education", "Skills"] if s not in sections]
    if missing_sections:
        ats_tips.append({
            "type": "format",
            "category": "Structure",
            "title": f"Missing Core Section: {missing_sections[0]}",
            "message": f"Ensure your resume has clearly labeled headings for: {', '.join(missing_sections)}.",
        })

    if not (contact_info["has_github"] or contact_info["has_linkedin"]):
        ats_tips.append({
            "type": "contact",
            "category": "Profiles",
            "title": "Add Professional Profile Links",
            "message": "Include clickable links to your GitHub profile and LinkedIn to boost recruiter engagement.",
        })

    if word_count < 200:
        ats_tips.append({
            "type": "length",
            "category": "Length",
            "title": "Resume May Be Too Brief",
            "message": f"Your resume currently has {word_count} words. Standard single-page technical resumes generally range between 350-700 words.",
        })
    elif word_count > 1000:
        ats_tips.append({
            "type": "length",
            "category": "Length",
            "title": "Consider Streamlining Length",
            "message": f"Your resume has {word_count} words. Aim for concise bullet points so recruiters can skim within 6-10 seconds.",
        })

    return {
        "target_role": profile["title"],
        "match_score": match_score,
        "ats_score": ats_score,
        "ats_checks": ats_checks,
        "ats_score_note": (
            "This is a heuristic content/readability estimate, not the measured accuracy "
            "or pass rate of a specific ATS. Visual layout and file parsing cannot be "
            "verified from extracted text."
        ),
        "formatted_resume": format_resume_for_ats(resume_text),
        "word_count": word_count,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "extra_skills": extra_skills,
        "contact_info": contact_info,
        "sections_detected": sections,
        "ats_tips": ats_tips,
        "recommended_roles": recommended_roles,
    }
