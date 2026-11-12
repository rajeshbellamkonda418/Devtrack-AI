const message = document.getElementById("message");
const skillsInput = document.getElementById("skills-input");
const skillButtons = document.querySelectorAll("[data-skill]");

function syncSkillSuggestions() {
    if (!skillsInput) return;

    const selected = new Set(
        skillsInput.value.split(",").map(skill => skill.trim().toLowerCase())
    );
    skillButtons.forEach(button => {
        const isSelected = selected.has(button.dataset.skill.toLowerCase());
        button.setAttribute("aria-pressed", String(isSelected));
        button.classList.toggle("is-selected", isSelected);
    });
}

skillButtons.forEach(button => {
    button.addEventListener("click", () => {
        if (!skillsInput) return;

        const selected = skillsInput.value.split(",")
            .map(skill => skill.trim())
            .filter(Boolean);
        const matchingIndex = selected.findIndex(
            skill => skill.toLowerCase() === button.dataset.skill.toLowerCase()
        );

        if (matchingIndex >= 0) {
            selected.splice(matchingIndex, 1);
        } else {
            selected.push(button.dataset.skill);
        }

        skillsInput.value = selected.join(", ");
        syncSkillSuggestions();
        skillsInput.focus();
    });
});

if (skillsInput) {
    skillsInput.addEventListener("input", syncSkillSuggestions);
    syncSkillSuggestions();
}

function notify(text, isError = false) {
    if (!message) return;
    message.textContent = text;
    message.style.color = isError ? "#ff9292" : "#c8f169";
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[char]));
}

async function loadJobs() {
    const tbody = document.getElementById("jobs-list");
    if (!tbody) return;

    try {
        const response = await fetch("/api/jobs");
        const jobs = await response.json();

        if (!response.ok) {
            throw new Error(jobs.error);
        }

        if (!jobs.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty">No applications yet.</td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = jobs.map(job => `
            <tr>
                <td>${escapeHtml(job.company)}</td>
                <td>${escapeHtml(job.role)}</td>
                <td>${escapeHtml(job.skills || "—")}</td>
                <td>
                    <select class="status-select" data-id="${job.id}">
                        ${["Applied", "Interview", "Selected", "Rejected"]
                            .map(status => `
                                <option ${job.status === status ? "selected" : ""}>
                                    ${status}
                                </option>
                            `).join("")}
                    </select>
                </td>
                <td>${escapeHtml(job.applied_date || "")}</td>
                <td>
                    <button class="delete-btn" data-delete="${job.id}">Delete</button>
                </td>
            </tr>
        `).join("");
    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty">${escapeHtml(error.message)}</td>
            </tr>
        `;
    }
}

const jobForm = document.getElementById("job-form");
jobForm?.addEventListener("submit", async event => {
    event.preventDefault();

    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries());

    try {
        const response = await fetch("/api/jobs", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not add application.");
        }

        formElement.reset();
        notify("Application added successfully!");
        loadJobs();
    } catch (error) {
        notify(error.message, true);
    }
});

document.getElementById("jobs-list")?.addEventListener("change", async event => {
    if (!event.target.matches(".status-select")) return;

    const id = event.target.dataset.id;

    try {
        const response = await fetch(`/api/jobs/${id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ status: event.target.value })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error);
        }

        notify("Application status updated!");
    } catch (error) {
        notify(error.message, true);
        loadJobs();
    }
});

document.getElementById("jobs-list")?.addEventListener("click", async event => {
    const button = event.target.closest("[data-delete]");

    if (!button) return;
    if (!confirm("Delete this application?")) return;

    try {
        const response = await fetch(`/api/jobs/${button.dataset.delete}`, { method: "DELETE" });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error);
        }

        notify("Application deleted!");
        loadJobs();
    } catch (error) {
        notify(error.message, true);
    }
});

const recommendForm = document.getElementById("recommend-form");
recommendForm?.addEventListener("submit", async event => {
    event.preventDefault();

    const input = document.getElementById("skills-input");
    if (!input) return;

    const skills = input.value.trim();
    const output = document.getElementById("recommendations");
    if (!output) return;

    output.innerHTML = "<p class='muted'>Finding suitable roles...</p>";

    try {
        const response = await fetch("/api/recommend", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ skills })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Could not load recommendations.");
        }

        if (!result.recommendations.length) {
            output.innerHTML = `<p class="muted">No close matches found. Try adding more skills.</p>`;
            return;
        }

        output.innerHTML = result.recommendations.map(item => `
            <article class="match-card">
                <h3>${escapeHtml(item.title)}</h3>
                <div class="match-score">${item.match}% similarity score</div>
                <div class="match-bar"><span style="width:${item.match}%"></span></div>
                <p class="muted">Profile skills: ${escapeHtml(item.matched_skills)}</p>
            </article>
        `).join("");

        animateMatches();
    } catch (error) {
        output.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    }
});

function animateMatches() {
    if (window.gsap) {
        gsap.from(".match-card", {
            y: 18,
            opacity: 0,
            duration: 0.5,
            stagger: 0.1,
            ease: "power2.out"
        });
    }
}

const homeJobSearchForm = document.getElementById("home-job-search-form");
const homeJobRole = document.getElementById("home-job-role");
const homeJobLocation = document.getElementById("home-job-location");
const homeJobType = document.getElementById("home-job-type");
const homeJobMessage = document.getElementById("home-job-message");
const homeJobResults = document.getElementById("home-job-results");
const homeJobLinks = document.getElementById("home-job-links");
const homeJobLinkList = document.getElementById("home-job-link-list");

function isSafeJobUrl(value) {
    try {
        return ["http:", "https:"].includes(new URL(value).protocol);
    } catch {
        return false;
    }
}

function renderHomeJobResults(data) {
    if (!homeJobLinkList || !homeJobLinks || !homeJobResults || !homeJobMessage) return;

    const links = (data.platform_links || [])
        .filter(platform => isSafeJobUrl(platform.url))
        .map(platform => {
            const link = document.createElement("a");
            link.href = platform.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = `${platform.name} ↗`;
            return link;
        });
    homeJobLinkList.replaceChildren(...links);
    homeJobLinks.hidden = links.length === 0;

    if (!data.jobs || data.jobs.length === 0) {
        homeJobMessage.textContent =
            `No live postings found for "${data.query}". Try the direct job-board searches above.`;
        homeJobResults.replaceChildren();
        return;
    }

    const cards = data.jobs.map(job => {
        const card = document.createElement("article");
        card.className = "home-job-card";

        const platform = document.createElement("p");
        platform.className = "home-job-platform";
        platform.textContent = job.platform || "Job board";

        const title = document.createElement("h3");
        title.textContent = job.title || "Untitled role";

        const company = document.createElement("p");
        company.className = "home-job-company";
        company.textContent = job.company || "Company not listed";

        const details = document.createElement("p");
        details.className = "home-job-details";
        details.textContent = `${job.location || "Remote"}${job.salary ? ` · ${job.salary}` : ""}`;

        const actions = document.createElement("div");
        actions.className = "home-job-actions";
        if (isSafeJobUrl(job.url)) {
            const applyLink = document.createElement("a");
            applyLink.href = job.url;
            applyLink.target = "_blank";
            applyLink.rel = "noopener noreferrer";
            applyLink.className = "primary-link search-link";
            applyLink.textContent = "View job ↗";
            actions.appendChild(applyLink);
        }

        card.append(platform, title, company, details, actions);
        return card;
    });

    homeJobResults.replaceChildren(...cards);
    homeJobMessage.textContent = `${data.jobs.length} job listing${data.jobs.length === 1 ? "" : "s"} found.`;
}

async function searchHomeJobs() {
    if (!homeJobSearchForm) return;

    const submitButton = homeJobSearchForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    homeJobMessage.textContent = "Searching current job listings...";
    homeJobResults.replaceChildren();

    try {
        const params = new URLSearchParams({
            role: homeJobRole.value.trim(),
            location: homeJobLocation.value.trim() || "Remote",
            employment_type: homeJobType.value
        });
        const response = await fetch(`/api/search-jobs?${params}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Could not load job listings.");
        }
        renderHomeJobResults(data);
    } catch (error) {
        homeJobMessage.textContent = error.message;
        homeJobMessage.classList.add("error");
    } finally {
        submitButton.disabled = false;
    }
}

if (homeJobSearchForm) {
    homeJobSearchForm.addEventListener("submit", event => {
        event.preventDefault();
        homeJobMessage.classList.remove("error");
        searchHomeJobs();
    });
}

window.addEventListener("DOMContentLoaded", () => {
    loadJobs();
    searchHomeJobs();

    const revealElements = document.querySelectorAll("[data-reveal]");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        revealElements.forEach(element => element.classList.add("is-visible"));
        return;
    }

    document.documentElement.classList.add("motion-ready");
    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -35px 0px" });
        revealElements.forEach(element => revealObserver.observe(element));
    } else {
        revealElements.forEach(element => element.classList.add("is-visible"));
    }

    if (!window.gsap) return;
    gsap.from(".hero-copy > *", {
        y: 24,
        opacity: 0,
        duration: 0.7,
        stagger: 0.12,
        clearProps: "all"
    });

    gsap.from(".hero-card", {
        x: 35,
        opacity: 0,
        duration: 0.8,
        delay: 0.2,
        clearProps: "all"
    });
});
