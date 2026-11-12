const dashboardSections = [...document.querySelectorAll("[data-dashboard-section]")];
const dashboardSectionLinks = [...document.querySelectorAll("[data-dashboard-target]")];

function showDashboardSection(sectionId) {
    const section = dashboardSections.find(item => item.id === sectionId);
    if (!section) return false;

    dashboardSections.forEach(item => {
        item.hidden = item !== section;
        item.classList.remove("dashboard-section-entering");
    });
    dashboardSectionLinks.forEach(link => {
        if (link.dataset.dashboardTarget === sectionId) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });
    if (animationsEnabled()) {
        requestAnimationFrame(() => {
            if (!section.hidden) {
                section.classList.add("dashboard-section-entering");
            }
        });
    }
    return true;
}

dashboardSectionLinks.forEach(link => {
    link.addEventListener("click", event => {
        const sectionId = link.dataset.dashboardTarget;
        if (!showDashboardSection(sectionId)) return;
        event.preventDefault();
        if (window.location.hash !== `#${sectionId}`) {
            window.history.pushState(null, "", `#${sectionId}`);
        }
    });
});

window.addEventListener("popstate", () => {
    showDashboardSection(window.location.hash.slice(1) || "overview");
});

const initialSection = window.location.hash.slice(1) || "overview";
if (!showDashboardSection(initialSection)) {
    showDashboardSection("overview");
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
}

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ";
    toast.innerHTML = `<span style="font-weight:700;">${icon}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add("is-hiding");
        setTimeout(() => toast.remove(), 320);
    }, 3500);
}

function animateCount(element, target, duration = 800) {
    if (!element) return;
    const start = parseInt(element.textContent, 10) || 0;
    if (start === target) return;
    if (!animationsEnabled()) {
        element.textContent = target;
        return;
    }
    const startTime = performance.now();

    function update(time) {
        const elapsed = time - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (target - start) * easeOut);
        element.textContent = current;
        if (progress < 1) {
            requestAnimationFrame(update);
        } else {
            element.textContent = target;
        }
    }
    requestAnimationFrame(update);
}

const applicationList = document.getElementById("applicationList");
const statuses = ["Applied", "Interview", "Selected", "Rejected"];
const skillsInput = document.getElementById("skills-input");
const skillButtons = document.querySelectorAll("[data-skill]");
let applications = [];
let currentApplicationsView = localStorage.getItem("devtrack_apps_view") || "table";

function setApplicationsView(mode) {
    currentApplicationsView = mode;
    localStorage.setItem("devtrack_apps_view", mode);
    const tableBtn = document.getElementById("tableViewBtn");
    const kanbanBtn = document.getElementById("kanbanViewBtn");
    const tableEl = document.getElementById("applicationList");
    const kanbanEl = document.getElementById("kanbanBoard");

    if (tableBtn && kanbanBtn && tableEl && kanbanEl) {
        if (mode === "kanban") {
            tableBtn.classList.remove("is-active");
            tableBtn.setAttribute("aria-pressed", "false");
            kanbanBtn.classList.add("is-active");
            kanbanBtn.setAttribute("aria-pressed", "true");
            tableEl.style.display = "none";
            kanbanEl.style.display = "grid";
        } else {
            kanbanBtn.classList.remove("is-active");
            kanbanBtn.setAttribute("aria-pressed", "false");
            tableBtn.classList.add("is-active");
            tableBtn.setAttribute("aria-pressed", "true");
            kanbanEl.style.display = "none";
            tableEl.style.display = "block";
        }
    }
}

const tableViewBtn = document.getElementById("tableViewBtn");
const kanbanViewBtn = document.getElementById("kanbanViewBtn");
if (tableViewBtn) {
    tableViewBtn.addEventListener("click", () => setApplicationsView("table"));
}
if (kanbanViewBtn) {
    kanbanViewBtn.addEventListener("click", () => setApplicationsView("kanban"));
}

function renderKanbanBoard(filteredJobs) {
    const kanban = document.getElementById("kanbanBoard");
    if (!kanban) return;
    kanban.replaceChildren();

    const statusConfigs = [
        { status: "Applied", label: "Applied", icon: "📝", dotClass: "dot-applied" },
        { status: "Interview", label: "Interview", icon: "💬", dotClass: "dot-interview" },
        { status: "Selected", label: "Selected", icon: "⭐", dotClass: "dot-selected" },
        { status: "Rejected", label: "Rejected", icon: "✕", dotClass: "dot-rejected" },
    ];

    statusConfigs.forEach(cfg => {
        const colJobs = filteredJobs.filter(job => job.status === cfg.status);
        const col = document.createElement("div");
        col.className = "kanban-col";

        const header = document.createElement("div");
        header.className = "kanban-col-header";
        header.innerHTML = `
            <div class="kanban-col-title">
                <span class="status-dot-sm ${cfg.dotClass}"></span>
                <span>${cfg.icon} ${cfg.label}</span>
            </div>
            <span class="kanban-count-pill">${colJobs.length}</span>
        `;
        col.appendChild(header);

        const cardsContainer = document.createElement("div");
        cardsContainer.className = "kanban-cards";

        if (!colJobs.length) {
            const empty = document.createElement("div");
            empty.className = "kanban-empty";
            empty.textContent = `No ${cfg.label.toLowerCase()} applications`;
            cardsContainer.appendChild(empty);
        } else {
            colJobs.forEach(job => {
                const card = document.createElement("div");
                card.className = `kanban-card status-${job.status.toLowerCase()}`;

                const top = document.createElement("div");
                top.className = "kanban-card-top";
                top.innerHTML = `
                    <div>
                        <div class="kanban-card-company">${escapeHtml(job.company)}</div>
                        <div class="kanban-card-role">${escapeHtml(job.role)}</div>
                    </div>
                `;
                card.appendChild(top);

                if (job.skills) {
                    const skillsWrap = document.createElement("div");
                    skillsWrap.className = "kanban-card-skills";
                    job.skills.split(/[, ]+/).filter(Boolean).slice(0, 4).forEach(skill => {
                        const tag = document.createElement("span");
                        tag.className = "kanban-skill-tag";
                        tag.textContent = skill;
                        skillsWrap.appendChild(tag);
                    });
                    card.appendChild(skillsWrap);
                }

                const footer = document.createElement("div");
                footer.className = "kanban-card-footer";

                const date = document.createElement("span");
                date.className = "kanban-card-date";
                date.textContent = (job.applied_date || "").slice(0, 10);

                const actions = document.createElement("div");
                actions.className = "kanban-card-actions";

                const select = document.createElement("select");
                select.className = "kanban-stage-select";
                select.setAttribute("aria-label", "Change status");
                statuses.forEach(s => {
                    const opt = document.createElement("option");
                    opt.value = s;
                    opt.textContent = s;
                    if (s === job.status) opt.selected = true;
                    select.appendChild(opt);
                });

                select.addEventListener("change", async () => {
                    const newStatus = select.value;
                    try {
                        const res = await fetch(`/api/jobs/${job.id}`, {
                            method: "PUT",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ status: newStatus })
                        });
                        if (!res.ok) throw new Error("Could not update status");
                        showToast(`Application moved to ${newStatus}!`, "success");
                        loadDashboard();
                    } catch (err) {
                        showToast(err.message, "error");
                        loadDashboard();
                    }
                });

                const delBtn = document.createElement("button");
                delBtn.className = "kanban-delete-btn";
                delBtn.type = "button";
                delBtn.title = "Delete application";
                delBtn.innerHTML = "🗑";
                delBtn.addEventListener("click", async () => {
                    if (!confirm(`Delete application for ${job.company} - ${job.role}?`)) return;
                    try {
                        const res = await fetch(`/api/jobs/${job.id}`, { method: "DELETE" });
                        if (!res.ok) throw new Error("Could not delete");
                        showToast("Application deleted", "info");
                        loadDashboard();
                    } catch (err) {
                        showToast(err.message, "error");
                    }
                });

                actions.append(select, delBtn);
                footer.append(date, actions);
                card.appendChild(footer);
                cardsContainer.appendChild(card);
            });
        }

        col.appendChild(cardsContainer);
        kanban.appendChild(col);
    });

    if (window.gsap && animationsEnabled()) {
        animateIn(kanban.querySelectorAll(".kanban-card"));
    }
}

function syncSkillSuggestions() {
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

function renderApplications() {
    const search = document.getElementById("application-search").value
        .trim().toLowerCase();
    const status = document.getElementById("status-filter").value;
    const filteredJobs = applications.filter(job => {
        const searchable = [job.company, job.role, job.skills || ""]
            .join(" ")
            .toLowerCase();
        return searchable.includes(search) && (!status || job.status === status);
    });

    const kanbanEl = document.getElementById("kanbanBoard");

    if (!filteredJobs.length) {
        document.getElementById("filter-help").textContent = applications.length
            ? "No applications match. Try changing or clearing your filters."
            : "Showing all applications.";
        applicationList.textContent = applications.length
            ? "No applications match these filters."
            : "No applications yet. Add one using the form above.";
        if (kanbanEl) {
            kanbanEl.innerHTML = `<div class="kanban-empty" style="grid-column: 1 / -1; padding: 40px;">${
                applications.length ? "No applications match these filters." : "No applications yet. Add one using the form above."
            }</div>`;
        }
        return;
    }

    document.getElementById("filter-help").textContent =
        `Showing ${filteredJobs.length} of ${applications.length} applications.`;

    const table = document.createElement("table");
    table.innerHTML = `
        <thead>
            <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Skills</th>
                <th>Status</th>
                <th>Date</th>
            </tr>
        </thead>
        <tbody></tbody>
    `;

    const tbody = table.querySelector("tbody");
    filteredJobs.forEach(job => {
        const row = document.createElement("tr");
        [job.company, job.role, job.skills || "—"].forEach(value => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        });
        const statusCell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `status-badge status-${job.status.toLowerCase()}`;
        badge.textContent = job.status;
        statusCell.appendChild(badge);
        row.appendChild(statusCell);
        const dateCell = document.createElement("td");
        dateCell.textContent = job.applied_date || "";
        row.appendChild(dateCell);
        tbody.appendChild(row);
    });

    applicationList.replaceChildren(table);
    renderKanbanBoard(filteredJobs);
    setApplicationsView(currentApplicationsView);
    animateIn(table.querySelectorAll("tbody tr"));
}

function animationsEnabled() {
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function animateIn(elements) {
    if (!window.gsap || !animationsEnabled() || !elements.length) return;
    window.gsap.from(elements, {
        y: 10,
        opacity: 0,
        duration: 0.35,
        stagger: 0.04,
        ease: "power2.out"
    });
}

function renderStatusChart() {
    const counts = Object.fromEntries(statuses.map(status => [
        status,
        applications.filter(job => job.status === status).length
    ]));
    const maxCount = Math.max(1, ...Object.values(counts));
    const chart = document.getElementById("statusChart");
    if (chart) {
        chart.replaceChildren();

        statuses.forEach(status => {
            const row = document.createElement("div");
            row.className = "status-chart-row";
            const label = document.createElement("span");
            label.className = "status-chart-label";
            label.textContent = status;
            const track = document.createElement("div");
            track.className = "status-chart-track";
            track.setAttribute("role", "img");
            track.setAttribute("aria-label", `${counts[status]} ${status} applications`);
            const bar = document.createElement("span");
            bar.className = `status-chart-bar status-${status.toLowerCase()}`;
            bar.style.width = `${(counts[status] / maxCount) * 100}%`;
            bar.dataset.width = bar.style.width;
            bar.style.width = "0";
            track.appendChild(bar);
            const count = document.createElement("span");
            count.className = "status-chart-count";
            count.textContent = counts[status];
            row.append(label, track, count);
            chart.appendChild(row);
        });

        if (window.gsap && animationsEnabled()) {
            window.gsap.to(chart.querySelectorAll(".status-chart-bar"), {
                width: index => chart.querySelectorAll(".status-chart-bar")[index].dataset.width,
                duration: 0.65,
                delay: 0.1,
                stagger: 0.08,
                ease: "power2.out"
            });
        } else {
            chart.querySelectorAll(".status-chart-bar").forEach(bar => {
                bar.style.width = bar.dataset.width;
            });
        }
    }

    const total = applications.length;
    const interviewCount = counts["Interview"] || 0;
    const selectedCount = counts["Selected"] || 0;
    const appliedCount = counts["Applied"] || 0;

    const interviewRate = total ? Math.round((interviewCount / total) * 100) : 0;
    const offerRate = total ? Math.round((selectedCount / total) * 100) : 0;
    const activeRate = total ? Math.round(((appliedCount + interviewCount) / total) * 100) : 0;

    const elInterviewRate = document.getElementById("analyticsInterviewRate");
    const elOfferRate = document.getElementById("analyticsOfferRate");
    const elActiveRate = document.getElementById("analyticsActiveRate");
    if (elInterviewRate) elInterviewRate.textContent = `${interviewRate}%`;
    if (elOfferRate) elOfferRate.textContent = `${offerRate}%`;
    if (elActiveRate) elActiveRate.textContent = `${activeRate}%`;

    const elInterviewRing = document.getElementById("interviewRing");
    const elOfferRing = document.getElementById("offerRing");
    const elActiveRing = document.getElementById("activeRing");
    if (elInterviewRing) elInterviewRing.setAttribute("stroke-dasharray", `${interviewRate}, 100`);
    if (elOfferRing) elOfferRing.setAttribute("stroke-dasharray", `${offerRate}, 100`);
    if (elActiveRing) elActiveRing.setAttribute("stroke-dasharray", `${activeRate}, 100`);
}

async function loadDashboard() {
    try {
        const response = await fetch("/api/jobs");
        const jobs = await response.json();

        if (!response.ok) {
            throw new Error(jobs.error || "Could not load applications.");
        }

        applications = jobs;
        const total = jobs.length;
        const companies = new Set(jobs.map(job => job.company.toLowerCase())).size;
        const interviews = jobs.filter(job => job.status === "Interview").length;
        const selected = jobs.filter(job => job.status === "Selected").length;

        animateCount(document.getElementById("totalApplications"), total);
        animateCount(document.getElementById("totalCompanies"), companies);
        animateCount(document.getElementById("interviewCount"), interviews);
        animateCount(document.getElementById("selectedCount"), selected);

        const exportBtn = document.getElementById("exportCsv");
        if (exportBtn) exportBtn.disabled = jobs.length === 0;

        renderApplications();
        renderStatusChart();
        animateIn(document.querySelectorAll(".stats .card"));
        return true;
    } catch (error) {
        if (applicationList) {
            applicationList.textContent = error.message;
            applicationList.classList.add("error");
        }
        return false;
    }
}

document.getElementById("application-search")
    .addEventListener("input", renderApplications);
document.getElementById("status-filter")
    .addEventListener("change", renderApplications);
document.getElementById("clear-filters").addEventListener("click", () => {
    document.getElementById("application-search").value = "";
    document.getElementById("status-filter").value = "";
    renderApplications();
    document.getElementById("application-search").focus();
});

document.getElementById("quick-add-form")
    .addEventListener("submit", async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const message = document.getElementById("quick-add-message");
        const submitButton = form.querySelector('button[type="submit"]');
        const payload = Object.fromEntries(new FormData(form).entries());
        message.textContent = "Adding application...";
        message.classList.remove("error");
        submitButton.disabled = true;
        submitButton.textContent = "Adding...";

        try {
            const response = await fetch("/api/jobs", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || "Could not add application.");
            }

            form.reset();
            document.getElementById("application-search").value = "";
            document.getElementById("status-filter").value = "";
            if (!await loadDashboard()) {
                throw new Error("Application was added, but the dashboard could not refresh.");
            }
            message.textContent = "Application added.";
            showToast("Application added to tracker!", "success");
            showDashboardSection("applications");
            document.getElementById("applications").scrollIntoView({
                behavior: animationsEnabled() ? "smooth" : "auto",
                block: "start"
            });
        } catch (error) {
            message.textContent = error.message;
            message.classList.add("error");
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = "Add application";
        }
    });

function csvCell(value) {
    let text = String(value ?? "");
    if (/^[\s]*[=+\-@]/.test(text)) {
        text = `'${text}`;
    }
    return `"${text.replace(/"/g, '""')}"`;
}

document.getElementById("exportCsv").addEventListener("click", () => {
    if (!applications.length) return;
    const headers = ["Company", "Role", "Skills", "Status", "Date"];
    const rows = applications.map(job => [
        job.company, job.role, job.skills || "", job.status, job.applied_date || ""
    ]);
    const csv = [headers, ...rows]
        .map(row => row.map(csvCell).join(","))
        .join("\r\n");
    const url = URL.createObjectURL(
        new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" })
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "devtrack-applications.csv";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
});

document.getElementById("recommend-form")
    .addEventListener("submit", async event => {
        event.preventDefault();

        const skills = skillsInput.value.trim();
        const output = document.getElementById("recommendationList");
        const submitButton = event.currentTarget.querySelector('button[type="submit"]');
        output.textContent = "Finding suitable roles...";
        output.classList.remove("error");
        submitButton.disabled = true;
        submitButton.textContent = "Finding...";

        try {
            const response = await fetch("/api/recommend", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ skills })
            });
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || "Could not load recommendations.");
            }

            if (!result.recommendations.length) {
                output.textContent = "No close matches found. Try adding more skills.";
                return;
            }

            const cards = document.createElement("div");
            cards.className = "recommendation-cards";
            result.recommendations.forEach(item => {
                const card = document.createElement("article");
                card.className = "card recommendation-card";
                const title = document.createElement("h3");
                title.textContent = item.title;
                const score = document.createElement("p");
                score.textContent = `${item.match}% similarity`;
                const skillsText = document.createElement("p");
                skillsText.textContent = `Profile skills: ${item.matched_skills}`;
                card.append(title, score, skillsText);
                cards.appendChild(card);
            });
            output.replaceChildren(cards);

            if (window.gsap) {
                animateIn(cards.querySelectorAll(".recommendation-card"));
            }
        } catch (error) {
            output.textContent = error.message;
            output.classList.add("error");
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = "Find Matches";
        }
    });

if (window.gsap && animationsEnabled()) {
    window.gsap.from(".main > h1, .main > .subtitle, .main > section", {
        y: 18,
        opacity: 0,
        duration: 0.5,
        stagger: 0.08,
        ease: "power2.out"
    });
}

loadDashboard();


// ============================================================
// RESUME ANALYZER CONTROLLER
// ============================================================
const targetRoleSelect = document.getElementById("target-role-select");
const customRoleContainer = document.getElementById("custom-role-container");
const customRoleInput = document.getElementById("custom-role-input");

const tabFileBtn = document.getElementById("tab-file-btn");
const tabTextBtn = document.getElementById("tab-text-btn");
const fileInputPane = document.getElementById("file-input-pane");
const textInputPane = document.getElementById("text-input-pane");

const dropZone = document.getElementById("dropZone");
const resumeFileInput = document.getElementById("resumeFileInput");
const selectedFileInfo = document.getElementById("selectedFileInfo");
const selectedFileName = document.getElementById("selectedFileName");
const removeFileBtn = document.getElementById("removeFileBtn");
const dropZoneContent = dropZone ? dropZone.querySelector(".drop-zone-content") : null;

const resumeTextInput = document.getElementById("resumeTextInput");
const resumeForm = document.getElementById("resume-form");
const analyzeResumeBtn = document.getElementById("analyzeResumeBtn");
const resumeMessage = document.getElementById("resumeMessage");
const resumeResults = document.getElementById("resumeResults");

let activeResumeMode = "file"; // "file" | "text"

if (targetRoleSelect) {
    targetRoleSelect.addEventListener("change", () => {
        if (targetRoleSelect.value === "custom") {
            customRoleContainer.style.display = "block";
            customRoleInput.focus();
        } else {
            customRoleContainer.style.display = "none";
        }
    });
}

if (tabFileBtn && tabTextBtn) {
    tabFileBtn.addEventListener("click", () => {
        activeResumeMode = "file";
        tabFileBtn.classList.add("is-active");
        tabTextBtn.classList.remove("is-active");
        fileInputPane.style.display = "block";
        textInputPane.style.display = "none";
    });

    tabTextBtn.addEventListener("click", () => {
        activeResumeMode = "text";
        tabTextBtn.classList.add("is-active");
        tabFileBtn.classList.remove("is-active");
        fileInputPane.style.display = "none";
        textInputPane.style.display = "block";
        resumeTextInput.focus();
    });
}

if (dropZone && resumeFileInput) {
    dropZone.addEventListener("click", e => {
        if (e.target !== removeFileBtn) {
            resumeFileInput.click();
        }
    });

    dropZone.addEventListener("dragover", e => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    ["dragleave", "dragend"].forEach(type => {
        dropZone.addEventListener(type, () => dropZone.classList.remove("drag-over"));
    });

    dropZone.addEventListener("drop", e => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length) {
            resumeFileInput.files = e.dataTransfer.files;
            handleFileSelected(e.dataTransfer.files[0]);
        }
    });

    resumeFileInput.addEventListener("change", () => {
        if (resumeFileInput.files.length) {
            handleFileSelected(resumeFileInput.files[0]);
        }
    });
}

function handleFileSelected(file) {
    if (!file) return;
    const isResumeFile = /\.(pdf|docx|txt)$/i.test(file.name || "");
    if (!isResumeFile) {
        if (resumeFileInput) resumeFileInput.value = "";
        if (selectedFileInfo) selectedFileInfo.style.display = "none";
        if (dropZoneContent) dropZoneContent.style.display = "block";
        resumeMessage.textContent = "Only PDF, DOCX, and TXT resume files are supported.";
        resumeMessage.classList.add("error");
        return;
    }
    if (dropZoneContent) dropZoneContent.style.display = "none";
    if (selectedFileInfo) {
        selectedFileInfo.style.display = "flex";
        selectedFileName.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    }
    if (resumeMessage) {
        resumeMessage.classList.remove("error");
    }
}

if (removeFileBtn) {
    removeFileBtn.addEventListener("click", e => {
        e.stopPropagation();
        resumeFileInput.value = "";
        if (selectedFileInfo) selectedFileInfo.style.display = "none";
        if (dropZoneContent) dropZoneContent.style.display = "block";
    });
}

function getSelectedRole() {
    if (!targetRoleSelect) return "";
    if (targetRoleSelect.value === "custom") {
        return (customRoleInput.value || "").trim();
    }
    return targetRoleSelect.value;
}

if (resumeForm) {
    resumeForm.addEventListener("submit", async event => {
        event.preventDefault();
        const role = getSelectedRole();
        if (targetRoleSelect && targetRoleSelect.value === "custom" && !role) {
            resumeMessage.textContent = "Please enter your custom target role or select automatic matching.";
            resumeMessage.classList.add("error");
            return;
        }

        resumeMessage.textContent = role
            ? "Analyzing resume for the selected role..."
            : "Analyzing resume and matching roles from its skills...";
        resumeMessage.classList.remove("error");
        analyzeResumeBtn.disabled = true;
        analyzeResumeBtn.textContent = "Analyzing...";

        try {
            let response;
            if (activeResumeMode === "file") {
                if (!resumeFileInput.files.length) {
                    throw new Error("Please select a resume file (.pdf, .docx, .txt).");
                }
                const selectedFile = resumeFileInput.files[0];
                if (!/\.(pdf|docx|txt)$/i.test(selectedFile.name || "")) {
                    throw new Error("Only PDF, DOCX, and TXT resume files are valid for analysis.");
                }
                const formData = new FormData();
                formData.append("resume", selectedFile);
                formData.append("role", role);

                response = await fetch("/api/analyze-resume", {
                    method: "POST",
                    body: formData
                });
            } else {
                const text = resumeTextInput.value.trim();
                if (!text) {
                    throw new Error("Please paste your resume text.");
                }
                response = await fetch("/api/analyze-resume", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ role, resume_text: text })
                });
            }

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || "Failed to analyze resume.");
            }

            renderResumeAnalysis(data);
            resumeMessage.textContent = "Analysis complete!";
        } catch (err) {
            resumeMessage.textContent = err.message;
            resumeMessage.classList.add("error");
        } finally {
            analyzeResumeBtn.disabled = false;
            analyzeResumeBtn.textContent = "Analyze Resume for Role ↗";
        }
    });
}

function renderResumeAnalysis(data) {
    if (!resumeResults) return;

    const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[character]);
    let scoreClass = "score-high";
    if (data.match_score < 50) scoreClass = "score-low";
    else if (data.match_score < 75) scoreClass = "score-mid";

    const matchedPills = data.matched_skills.length
        ? data.matched_skills.map(s => `<span class="skill-tag tag-matched">✓ ${escapeHtml(s)}</span>`).join("")
        : '<span class="skill-help">None detected matching role core skills</span>';

    const missingPills = data.missing_skills.length
        ? data.missing_skills.map(s => `<span class="skill-tag tag-missing">✕ ${escapeHtml(s)}</span>`).join("")
        : '<span class="skill-help">All key target role skills covered!</span>';

    const extraPills = data.extra_skills.length
        ? data.extra_skills.map(s => `<span class="skill-tag tag-extra">${escapeHtml(s)}</span>`).join("")
        : '<span class="skill-help">No additional secondary skills found</span>';

    const recommendedRolesHtml = (data.recommended_roles || []).length
        ? (data.recommended_roles || []).map(role => `
            <div class="resume-role-option">
                <button type="button" class="resume-role-chip" data-role-name="${escapeHtml(role.title)}">
                    <span>${escapeHtml(role.title)}</span>
                    <strong>${role.match}%</strong>
                </button>
                <small>Matched skills: ${(role.matched_skills || []).map(escapeHtml).join(", ")}</small>
            </div>
        `).join("")
        : '<span class="skill-help">No strong role matches found yet.</span>';
    const topRecommendedRole = (data.recommended_roles || [])[0];

    const metaItems = [
        `<span class="meta-pill">📝 ${data.word_count} Words</span>`,
        `<span class="meta-pill">📑 ${data.sections_detected.length} Sections Found</span>`
    ];
    if (data.contact_info.email) metaItems.push(`<span class="meta-pill">✉ ${escapeHtml(data.contact_info.email)}</span>`);
    if (data.contact_info.has_github) metaItems.push('<span class="meta-pill">🐙 GitHub Found</span>');
    if (data.contact_info.has_linkedin) metaItems.push('<span class="meta-pill">💼 LinkedIn Found</span>');

    const tipsHtml = data.ats_tips.map(tip => `
        <div class="tip-card">
            <div class="tip-title">${escapeHtml(tip.title)}</div>
            <div class="tip-message">${escapeHtml(tip.message)}</div>
        </div>
    `).join("");
    const atsScoreClass = data.ats_score >= 80
        ? "score-high"
        : data.ats_score >= 60 ? "score-mid" : "score-low";
    const atsChecksHtml = data.ats_checks.map(check => `
        <div class="ats-check">
            <div class="ats-check-heading">
                <strong>${escapeHtml(check.name)}</strong>
                <span>${check.score}/${check.max_score}</span>
            </div>
            <div class="ats-check-track" aria-hidden="true">
                <span style="width:${Math.round(check.score / check.max_score * 100)}%"></span>
            </div>
            <p>${escapeHtml(check.detail)}</p>
        </div>
    `).join("");

    resumeResults.innerHTML = `
        <div class="resume-header-stats">
            <div class="score-circle ${scoreClass}">
                <span class="score-number">${data.match_score}%</span>
                <span class="score-label">Role Match</span>
            </div>
            <div class="resume-overview">
                <h3>${escapeHtml(data.target_role)} Match Report</h3>
                <p>Compatibility evaluated using NLP parsing and role-specific skill weighting.</p>
                <div class="resume-meta-pills">
                    ${metaItems.join("")}
                </div>
            </div>
            <div>
                <button type="button" id="searchFromAnalysisBtn" class="action-trigger-btn">
                    Search Jobs for ${escapeHtml(data.target_role)} ↘
                </button>
            </div>
        </div>

        <section class="ats-score-panel" aria-labelledby="ats-score-title">
            <div class="ats-score-summary">
                <div class="score-circle ${atsScoreClass}">
                    <span class="score-number">${data.ats_score}%</span>
                    <span class="score-label">ATS Content</span>
                </div>
                <div>
                    <h4 id="ats-score-title">ATS-readability estimate</h4>
                    <p>${escapeHtml(data.ats_score_note)}</p>
                </div>
            </div>
            <div class="ats-checks-grid">${atsChecksHtml}</div>
        </section>

        <div class="skills-comparison-grid">
            <div class="skills-col matched">
                <h4>✓ Matched Core Skills (${data.matched_skills.length})</h4>
                <div class="skills-pill-box">${matchedPills}</div>
            </div>
            <div class="skills-col missing">
                <h4>✕ Missing Skills to Add (${data.missing_skills.length})</h4>
                <div class="skills-pill-box">${missingPills}</div>
            </div>
        </div>

        <div class="skills-col" style="background:#0f172a; border:1px solid #334155; border-radius:10px; padding:18px;">
            <h4 style="color:#60a5fa; font-size:14px; margin-bottom:10px;">🌟 Additional Skills in Resume (${data.extra_skills.length})</h4>
            <div class="skills-pill-box">${extraPills}</div>
        </div>

        <div class="skills-col" style="background:#111827; border:1px solid #334155; border-radius:10px; padding:18px;">
            <h4 style="color:#4ade80; font-size:14px; margin-bottom:10px;">AI Job Roles Matching This Resume</h4>
            <p>Ranked from the skills detected in your resume. Select a role to load live openings.</p>
            <div class="skills-pill-box resume-role-box">${recommendedRolesHtml}</div>
            <div class="resume-jobs-panel">
                <h4 id="resumeJobsHeading">Live openings for your best-matched role</h4>
                <div id="resumeRecommendedJobs" class="resume-recommended-jobs" aria-live="polite">
                    <p class="muted-note">Loading jobs matching your resume...</p>
                </div>
            </div>
        </div>

        <div class="ats-tips-container">
            <h4>🎯 ATS Optimization & Actionable Feedback</h4>
            <div class="tips-list">${tipsHtml}</div>
        </div>

        <section class="ats-conversion" aria-labelledby="ats-conversion-title">
            <div>
                <h4 id="ats-conversion-title">Create an ATS-friendly text version</h4>
                <p>Standardized headings and simple bullets; your original content is kept in its current order and no claims are added.</p>
            </div>
            <button type="button" id="showAtsVersionBtn" class="secondary-button">Preview ATS version</button>
            <div id="atsVersionPanel" class="ats-version-panel" hidden>
                <label for="atsVersionText">Formatted resume text</label>
                <textarea id="atsVersionText" rows="12" readonly></textarea>
                <div class="ats-version-actions">
                    <button type="button" id="downloadAtsVersionBtn" class="secondary-button">Download .txt</button>
                    <button type="button" id="copyAtsVersionBtn" class="text-button">Copy text</button>
                    <span id="atsConversionMessage" aria-live="polite"></span>
                </div>
            </div>
        </section>
    `;

    resumeResults.style.display = "flex";
    resumeResults.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (topRecommendedRole) {
        loadResumeRecommendedJobs(topRecommendedRole.title);
    } else {
        document.getElementById("resumeRecommendedJobs").textContent =
            "No matching roles were found from the skills in this resume.";
    }

    const searchFromAnalysisBtn = document.getElementById("searchFromAnalysisBtn");
    if (searchFromAnalysisBtn) {
        searchFromAnalysisBtn.addEventListener("click", () => {
            const jobSearchRole = document.getElementById("jobSearchRole");
            if (jobSearchRole) {
                jobSearchRole.value = data.target_role;
                updateSalarySnapshot();
                showDashboardSection("job-search");
                document.getElementById("job-search").scrollIntoView({ behavior: "smooth" });
                executeJobSearch(data.target_role, "Remote", "all");
            }
        });
    }

    document.querySelectorAll(".resume-role-chip").forEach(button => {
        button.addEventListener("click", () => {
            const roleName = button.dataset.roleName;
            if (roleName) loadResumeRecommendedJobs(roleName);
        });
    });

    const atsVersionPanel = document.getElementById("atsVersionPanel");
    const atsVersionText = document.getElementById("atsVersionText");
    const atsConversionMessage = document.getElementById("atsConversionMessage");
    document.getElementById("showAtsVersionBtn").addEventListener("click", event => {
        atsVersionPanel.hidden = !atsVersionPanel.hidden;
        event.currentTarget.textContent = atsVersionPanel.hidden
            ? "Preview ATS version"
            : "Hide ATS version";
        if (!atsVersionPanel.hidden) atsVersionText.value = data.formatted_resume;
    });
    document.getElementById("downloadAtsVersionBtn").addEventListener("click", () => {
        const file = new Blob([data.formatted_resume], { type: "text/plain;charset=utf-8" });
        const link = document.createElement("a");
        const downloadUrl = URL.createObjectURL(file);
        link.href = downloadUrl;
        link.download = "ats-friendly-resume.txt";
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
        atsConversionMessage.textContent = "ATS-friendly text file downloaded.";
    });
    document.getElementById("copyAtsVersionBtn").addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(data.formatted_resume);
            atsConversionMessage.textContent = "ATS-friendly text copied.";
        } catch {
            atsConversionMessage.textContent = "Copy was blocked by the browser. Select the preview text and copy it manually.";
        }
    });

    if (window.gsap && animationsEnabled()) {
        animateIn(resumeResults.querySelectorAll(".skills-col, .ats-tips-container, .score-circle"));
    }
}

let resumeJobsRequestId = 0;

async function loadResumeRecommendedJobs(role) {
    const jobsContainer = document.getElementById("resumeRecommendedJobs");
    const heading = document.getElementById("resumeJobsHeading");
    if (!jobsContainer || !role) return;

    const requestId = ++resumeJobsRequestId;
    if (heading) heading.textContent = `Live openings for ${role}`;
    jobsContainer.textContent = "Searching live jobs...";

    try {
        const params = new URLSearchParams({
            role,
            location: "Remote",
            platform: "all",
            employment_type: "all"
        });
        const response = await fetch(`/api/search-jobs?${params}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Could not load matching jobs.");
        }
        if (requestId !== resumeJobsRequestId) return;

        const jobs = Array.isArray(data.jobs) ? data.jobs.slice(0, 5) : [];
        if (!jobs.length) {
            jobsContainer.textContent = `No live postings found for ${role} right now. Try another suggested role or use the job-board links in Job Search.`;
            return;
        }

        const cards = jobs.map(job => {
            const card = document.createElement("article");
            card.className = "resume-job-card";

            const title = document.createElement("strong");
            title.textContent = job.title || "Untitled role";
            const details = document.createElement("p");
            details.textContent = [job.company, job.location, job.platform]
                .filter(Boolean)
                .join(" · ");
            card.append(title, details);

            if (isHttpUrl(job.url)) {
                const link = document.createElement("a");
                link.href = job.url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = "View opening";
                card.appendChild(link);
            }
            return card;
        });
        jobsContainer.replaceChildren(...cards);
    } catch (error) {
        if (requestId !== resumeJobsRequestId) return;
        jobsContainer.textContent = error.message || "Could not load matching jobs.";
    }
}


// ============================================================
// MULTI-PLATFORM JOB SEARCH CONTROLLER
// ============================================================
const jobSearchForm = document.getElementById("jobSearchForm");
const jobSearchRole = document.getElementById("jobSearchRole");
const jobSearchLocation = document.getElementById("jobSearchLocation");
const jobSearchPlatform = document.getElementById("jobSearchPlatform");
const jobSearchType = document.getElementById("jobSearchType");
const jobSearchBtn = document.getElementById("jobSearchBtn");
const platformLinksBar = document.getElementById("platformLinksBar");
const platformLinksList = document.getElementById("platformLinksList");
const jobSearchResults = document.getElementById("jobSearchResults");
const salaryExperience = document.getElementById("salaryExperience");
const salaryRoleLabel = document.getElementById("salaryRoleLabel");
const salaryRange = document.getElementById("salaryRange");
const salaryRangeBar = document.getElementById("salaryRangeBar");

const salaryBenchmarks = [
    {
        match: /machine learning|ml engineer|artificial intelligence|\bai engineer\b|ai application/,
        label: "Machine Learning Engineer",
        ranges: { entry: [600000, 1200000], mid: [1200000, 2500000], senior: [2200000, 4500000] }
    },
    {
        match: /data analyst|business intelligence|\bbi analyst\b/,
        label: "Data Analyst",
        ranges: { entry: [400000, 800000], mid: [800000, 1500000], senior: [1400000, 2500000] }
    },
    {
        match: /data engineer|analytics engineer/,
        label: "Data Engineer",
        ranges: { entry: [600000, 1200000], mid: [1200000, 2400000], senior: [2200000, 4000000] }
    },
    {
        match: /cybersecurity|security analyst|security engineer/,
        label: "Cybersecurity Specialist",
        ranges: { entry: [450000, 900000], mid: [900000, 1800000], senior: [1600000, 3200000] }
    },
    {
        match: /ui.?ux|product designer|ux designer/,
        label: "Product / UX Designer",
        ranges: { entry: [400000, 800000], mid: [800000, 1600000], senior: [1500000, 2800000] }
    },
    {
        match: /\bgo backend\b/,
        label: "Go Backend Developer",
        ranges: { entry: [600000, 1200000], mid: [1200000, 2500000], senior: [2200000, 4500000] }
    },
    {
        match: /frontend|front.end|react developer|web developer/,
        label: "Frontend Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 1800000], senior: [1600000, 3000000] }
    },
    {
        match: /backend|back.end|api developer/,
        label: "Backend Developer",
        ranges: { entry: [500000, 1000000], mid: [1000000, 2200000], senior: [1800000, 3800000] }
    },
    {
        match: /full.?stack/,
        label: "Full-Stack Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 2000000], senior: [1700000, 3500000] }
    },
    {
        match: /devops|cloud engineer|site reliability|\bsre\b/,
        label: "Cloud / DevOps Engineer",
        ranges: { entry: [550000, 1100000], mid: [1100000, 2300000], senior: [2000000, 4000000] }
    },
    {
        match: /qa|quality assurance|test automation/,
        label: "QA Automation Engineer",
        ranges: { entry: [350000, 700000], mid: [700000, 1400000], senior: [1200000, 2400000] }
    },
    {
        match: /mobile|ios developer|android developer/,
        label: "Mobile Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 2000000], senior: [1800000, 3500000] }
    },
    {
        match: /c\+\+|systems developer|systems engineer|rust|golang/,
        label: "Systems Engineer",
        ranges: { entry: [500000, 1200000], mid: [1200000, 2500000], senior: [2200000, 4500000] }
    },
    {
        match: /python/,
        label: "Python Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 2000000], senior: [1800000, 3500000] }
    },
    {
        match: /java/,
        label: "Java Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 2000000], senior: [1800000, 3500000] }
    },
    {
        match: /\.net|dotnet/,
        label: ".NET Developer",
        ranges: { entry: [400000, 800000], mid: [800000, 1700000], senior: [1500000, 3000000] }
    },
    {
        match: /javascript|node\.?js/,
        label: "JavaScript Developer",
        ranges: { entry: [450000, 900000], mid: [900000, 2000000], senior: [1700000, 3500000] }
    },
    {
        match: /\bgo\b/,
        label: "Go Developer",
        ranges: { entry: [600000, 1200000], mid: [1200000, 2500000], senior: [2200000, 4500000] }
    },
    {
        match: /php/,
        label: "PHP Developer",
        ranges: { entry: [350000, 700000], mid: [700000, 1500000], senior: [1300000, 2500000] }
    },
    {
        match: /custom/,
        label: "Software Engineer",
        ranges: { entry: [400000, 800000], mid: [800000, 1800000], senior: [1500000, 3000000] }
    },
    {
        match: /developer|engineer/,
        label: "Software Engineer",
        ranges: { entry: [400000, 800000], mid: [800000, 1800000], senior: [1500000, 3000000] }
    },
];

function updateSalarySnapshot() {
    const role = jobSearchRole.value.trim();
    const normalizedRole = role.toLowerCase();
    const benchmark = salaryBenchmarks.find(item => item.match.test(normalizedRole))
        || salaryBenchmarks[salaryBenchmarks.length - 1];
    const experience = salaryExperience.value;
    const [minimum, maximum] = benchmark.ranges[experience];
    const experienceLabel = salaryExperience.selectedOptions[0].textContent;
    const formatSalary = amount => {
        const lakhs = amount / 100000;
        return `${lakhs % 1 === 0 ? lakhs : lakhs.toFixed(1)}L`;
    };

    salaryRoleLabel.textContent = `${role || benchmark.label} · ${experienceLabel}`;
    salaryRange.textContent = `₹${formatSalary(minimum)}–${formatSalary(maximum)} per year`;
    salaryRangeBar.style.left = `${Math.max(0, ((minimum - 300000) / 5000000) * 100)}%`;
    salaryRangeBar.style.width = `${Math.min(100, ((maximum - minimum) / 5000000) * 100)}%`;
}

if (jobSearchRole && salaryExperience) {
    jobSearchRole.addEventListener("input", updateSalarySnapshot);
    salaryExperience.addEventListener("change", updateSalarySnapshot);
    updateSalarySnapshot();
}

if (jobSearchForm) {
    jobSearchForm.addEventListener("submit", event => {
        event.preventDefault();
        const role = jobSearchRole.value.trim();
        const location = jobSearchLocation.value.trim() || "Remote";
        const platform = jobSearchPlatform.value;
        const employmentType = jobSearchType.value;
        if (!role) return;
        executeJobSearch(role, location, platform, employmentType);
    });
}

async function executeJobSearch(
    role,
    location = "Remote",
    platform = "all",
    employmentType = "all"
) {
    if (!jobSearchResults) return;

    const cleanedRole = (role || "").trim();
    if (!cleanedRole) {
        const message = document.createElement("p");
        message.className = "muted-note";
        message.textContent = "Enter a role to search live job openings.";
        jobSearchResults.replaceChildren(message);
        if (platformLinksBar && platformLinksList) {
            platformLinksList.replaceChildren();
            platformLinksBar.style.display = "none";
        }
        return;
    }

    jobSearchResults.innerHTML = '<p class="muted-note">Searching live jobs across platforms...</p>';
    if (jobSearchBtn) {
        jobSearchBtn.disabled = true;
        jobSearchBtn.textContent = "Searching...";
    }

    try {
        const queryParams = new URLSearchParams({
            role: cleanedRole,
            location,
            platform,
            employment_type: employmentType
        });
        const response = await fetch(`/api/search-jobs?${queryParams}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Failed to search jobs.");
        }

        renderJobSearchResults(data);
    } catch (err) {
        const message = document.createElement("p");
        message.className = "muted-note error";
        message.textContent = err.message;
        jobSearchResults.replaceChildren(message);
    } finally {
        if (jobSearchBtn) {
            jobSearchBtn.disabled = false;
            jobSearchBtn.textContent = "Search Jobs";
        }
    }
}

function renderJobSearchResults(data) {
    if (platformLinksBar && platformLinksList) {
        const links = Array.isArray(data.platform_links)
            ? data.platform_links.filter(platform => isHttpUrl(platform.url))
            : [];

        if (!links.length) {
            platformLinksList.replaceChildren();
            platformLinksBar.style.display = "none";
        } else {
            const chips = links.map(platform => {
                const link = document.createElement("a");
                link.className = "platform-chip";
                link.href = platform.url;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = `${platform.name} ↗`;
                return link;
            });
            platformLinksList.replaceChildren(...chips);
            platformLinksBar.style.display = "flex";
        }
    }

    if (!data.jobs || !data.jobs.length) {
        const message = document.createElement("p");
        message.className = "muted-note";
        message.textContent = data.query
            ? `No live postings found matching "${data.query}". Use the direct platform links above to search on LinkedIn, Indeed, and Glassdoor!`
            : "Enter a role to search live job openings.";
        jobSearchResults.replaceChildren(message);
        return;
    }

    const cardsContainer = document.createElement("div");
    cardsContainer.className = "job-cards-grid";

    data.jobs.forEach(job => {
        const card = document.createElement("article");
        card.className = "job-card";

        const platformSlug = (job.platform || "remoteok").toLowerCase().replace(/[^a-z]/g, "");
        const topRow = document.createElement("div");
        topRow.className = "job-card-top";
        const platformBadge = document.createElement("span");
        platformBadge.className = `job-platform-badge platform-${platformSlug}`;
        platformBadge.textContent = job.platform || "Job board";
        const posted = document.createElement("span");
        posted.textContent = job.posted || "Recent";
        topRow.append(platformBadge, posted);

        const title = document.createElement("h3");
        title.textContent = job.title || "Untitled role";
        const company = document.createElement("div");
        company.className = "job-company";
        company.textContent = job.company || "Company not listed";

        const details = document.createElement("div");
        details.className = "job-details-row";
        const location = document.createElement("span");
        location.textContent = `📍 ${job.location || "Remote"}`;
        details.appendChild(location);
        if (job.salary) {
            const salary = document.createElement("span");
            salary.className = "job-tag job-salary";
            salary.textContent = `💰 ${job.salary}`;
            details.appendChild(salary);
        }

        const tags = document.createElement("div");
        tags.className = "job-tags-row";
        (job.tags || []).forEach(tag => {
            const tagElement = document.createElement("span");
            tagElement.className = "job-tag";
            tagElement.textContent = tag;
            tags.appendChild(tagElement);
        });

        const actions = document.createElement("div");
        actions.className = "job-card-actions";
        if (isHttpUrl(job.url)) {
            const applyLink = document.createElement("a");
            applyLink.className = "job-apply-link";
            applyLink.href = job.url;
            applyLink.target = "_blank";
            applyLink.rel = "noopener noreferrer";
            applyLink.textContent = "Apply ↗";
            actions.appendChild(applyLink);
        }
        const trackBtn = document.createElement("button");
        trackBtn.type = "button";
        trackBtn.className = "job-track-btn";
        trackBtn.textContent = "Track in DevTrack +";
        actions.appendChild(trackBtn);

        card.append(topRow, title, company, details, tags, actions);
        trackBtn.addEventListener("click", async () => {
            await handleTrackJob(
                trackBtn,
                job.company || "Unknown company",
                job.title || "Untitled role",
                (job.tags || []).join(", ")
            );
        });

        cardsContainer.appendChild(card);
    });

    jobSearchResults.replaceChildren(cardsContainer);
    if (window.gsap && animationsEnabled()) {
        animateIn(cardsContainer.querySelectorAll(".job-card"));
    }
}

function isHttpUrl(value) {
    try {
        return ["http:", "https:"].includes(new URL(value).protocol);
    } catch {
        return false;
    }
}

async function handleTrackJob(btn, company, role, skills) {
    btn.disabled = true;
    btn.textContent = "Saving...";

    try {
        const response = await fetch("/api/jobs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                company: (company || "").slice(0, 120),
                role: (role || "").slice(0, 120),
                skills: skills || "",
                status: "Applied"
            })
        });

        const res = await response.json();
        if (!response.ok) {
            throw new Error(res.error || "Could not track job");
        }

        btn.textContent = "Tracked! ✓";
        btn.classList.add("is-tracked");
        loadDashboard();
    } catch (err) {
        btn.disabled = false;
        btn.textContent = "Retry Tracking";
        alert(`Error tracking job: ${err.message}`);
    }
}

const interviewQuestionForm = document.getElementById("interview-question-form");
const interviewTopic = document.getElementById("interview-topic");
const interviewLevel = document.getElementById("interview-level");
const interviewQuestionList = document.getElementById("interview-question-list");
const interviewQuestionCount = document.getElementById("interview-question-count");
let interviewQuestionRequest = 0;

let currentInterviewQuestions = [];
let quizIndex = 0;
let quizTimerSec = 60;
let quizTimerId = null;
let quizTimerRunning = false;
let currentInterviewMode = "browse";
let quizUserRatings = {};

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function stopQuizTimer() {
    if (quizTimerId) {
        clearInterval(quizTimerId);
        quizTimerId = null;
    }
    quizTimerRunning = false;
}

function startQuizTimer(resetSeconds = 60) {
    stopQuizTimer();
    quizTimerSec = resetSeconds;
    quizTimerRunning = true;
    updateQuizTimerDisplay();

    quizTimerId = setInterval(() => {
        if (quizTimerSec > 0) {
            quizTimerSec -= 1;
            updateQuizTimerDisplay();
            if (quizTimerSec === 0) {
                stopQuizTimer();
                showToast("Time's up! Review the sample answer.", "info");
            }
        } else {
            stopQuizTimer();
        }
    }, 1000);
}

function updateQuizTimerDisplay() {
    const display = document.getElementById("quizTimerDisplay");
    if (!display) return;
    display.textContent = formatTime(quizTimerSec);
    display.classList.toggle("is-warning", quizTimerSec <= 10 && quizTimerSec > 0);
}

function renderQuizCard() {
    const panel = document.getElementById("interview-quiz-panel");
    if (!panel) return;

    if (!currentInterviewQuestions.length) {
        panel.innerHTML = `<p class="muted-note">No questions loaded. Please select a domain and difficulty above.</p>`;
        return;
    }

    if (quizIndex >= currentInterviewQuestions.length) {
        const masteredCount = Object.values(quizUserRatings).filter(r => r === "mastered").length;
        const total = currentInterviewQuestions.length;
        const scorePercent = Math.round((masteredCount / total) * 100);

        panel.innerHTML = `
            <div style="text-align: center; padding: 20px 0;">
                <div style="font-size: 3rem; margin-bottom: 12px;">🎉</div>
                <h3 style="font-size: 1.5rem; color: #f8fafc; margin-bottom: 8px;">Practice Session Complete!</h3>
                <p style="color: #94a3b8; max-width: 440px; margin: 0 auto 20px;">
                    You mastered <strong>${masteredCount}</strong> of <strong>${total}</strong> questions (${scorePercent}% confidence).
                </p>
                <div style="display: flex; justify-content: center; gap: 12px;">
                    <button type="button" id="quizRestartBtn" class="primary-button">Practice Again ↺</button>
                    <button type="button" id="quizReviewListBtn" class="secondary-button">Browse All List</button>
                </div>
            </div>
        `;
        document.getElementById("quizRestartBtn")?.addEventListener("click", () => {
            quizIndex = 0;
            quizUserRatings = {};
            renderQuizCard();
        });
        document.getElementById("quizReviewListBtn")?.addEventListener("click", () => {
            setInterviewMode("browse");
        });
        return;
    }

    const item = currentInterviewQuestions[quizIndex];
    const itemRating = quizUserRatings[quizIndex] || "";

    panel.innerHTML = `
        <div class="quiz-header">
            <div class="quiz-meta">
                <span class="quiz-progress-text">Question ${quizIndex + 1} of ${currentInterviewQuestions.length}</span>
                <span class="quiz-badge">${escapeHtml(item.topic_name)}</span>
                <span class="question-level level-${item.level}">${item.level}</span>
            </div>
            <div class="quiz-timer-container">
                <div id="quizTimerDisplay" class="quiz-timer-display">${formatTime(quizTimerSec)}</div>
                <button type="button" id="quizTimerToggleBtn" class="quiz-timer-btn">${quizTimerRunning ? "Pause" : "Start"}</button>
                <button type="button" id="quizTimerResetBtn" class="quiz-timer-btn" title="Reset to 60s">↺ 60s</button>
            </div>
        </div>

        <div class="quiz-question-box">
            <h3 class="quiz-question-title">${escapeHtml(item.question)}</h3>
        </div>

        <div>
            <button type="button" id="quizToggleAnswerBtn" class="quiz-answer-toggle-btn">Reveal Sample Answer ↘</button>
            <div id="quizAnswerBox" class="quiz-answer-box" style="display: none;">
                <strong>Sample Answer Key</strong>
                <div id="quizAnswerContent"></div>
            </div>
        </div>

        <div class="quiz-footer">
            <div class="quiz-rating-group">
                <span style="font-size:0.85rem; color:#94a3b8; margin-right:4px;">Self-rating:</span>
                <button type="button" id="quizRateMastered" class="quiz-rating-btn mastered ${itemRating === 'mastered' ? 'is-active' : ''}">Mastered ✓</button>
                <button type="button" id="quizRateReview" class="quiz-rating-btn review ${itemRating === 'review' ? 'is-active' : ''}">Needs Review 🔄</button>
            </div>
            <div class="quiz-nav-group">
                <button type="button" id="quizPrevBtn" class="quiz-nav-btn" ${quizIndex === 0 ? "disabled" : ""}>← Previous</button>
                <button type="button" id="quizNextBtn" class="quiz-nav-btn">${quizIndex === currentInterviewQuestions.length - 1 ? "Finish Session 🎉" : "Next Question →"}</button>
            </div>
        </div>
    `;

    const answerContent = document.getElementById("quizAnswerContent");
    if (answerContent) {
        answerContent.textContent = item.answer;
    }

    document.getElementById("quizTimerToggleBtn")?.addEventListener("click", () => {
        if (quizTimerRunning) {
            stopQuizTimer();
            const btn = document.getElementById("quizTimerToggleBtn");
            if (btn) btn.textContent = "Resume";
        } else {
            startQuizTimer(quizTimerSec || 60);
            const btn = document.getElementById("quizTimerToggleBtn");
            if (btn) btn.textContent = "Pause";
        }
    });

    document.getElementById("quizTimerResetBtn")?.addEventListener("click", () => {
        startQuizTimer(60);
        const toggleBtn = document.getElementById("quizTimerToggleBtn");
        if (toggleBtn) toggleBtn.textContent = "Pause";
    });

    const toggleAnswerBtn = document.getElementById("quizToggleAnswerBtn");
    const answerBox = document.getElementById("quizAnswerBox");
    if (toggleAnswerBtn && answerBox) {
        toggleAnswerBtn.addEventListener("click", () => {
            const isHidden = answerBox.style.display === "none";
            answerBox.style.display = isHidden ? "block" : "none";
            toggleAnswerBtn.textContent = isHidden ? "Hide Answer ↗" : "Reveal Sample Answer ↘";
        });
    }

    document.getElementById("quizRateMastered")?.addEventListener("click", () => {
        quizUserRatings[quizIndex] = "mastered";
        renderQuizCard();
    });

    document.getElementById("quizRateReview")?.addEventListener("click", () => {
        quizUserRatings[quizIndex] = "review";
        renderQuizCard();
    });

    document.getElementById("quizPrevBtn")?.addEventListener("click", () => {
        if (quizIndex > 0) {
            quizIndex -= 1;
            startQuizTimer(60);
            renderQuizCard();
        }
    });

    document.getElementById("quizNextBtn")?.addEventListener("click", () => {
        quizIndex += 1;
        startQuizTimer(60);
        renderQuizCard();
    });

    if (window.gsap && animationsEnabled()) {
        window.gsap.from(".quiz-question-box", {
            y: 8,
            opacity: 0,
            duration: 0.25,
            ease: "power2.out"
        });
    }
}

function setInterviewMode(mode) {
    currentInterviewMode = mode;
    const browseBtn = document.getElementById("browseModeBtn");
    const quizBtn = document.getElementById("quizModeBtn");
    const listEl = document.getElementById("interview-question-list");
    const quizEl = document.getElementById("interview-quiz-panel");

    if (browseBtn && quizBtn && listEl && quizEl) {
        if (mode === "quiz") {
            browseBtn.classList.remove("is-active");
            browseBtn.setAttribute("aria-pressed", "false");
            quizBtn.classList.add("is-active");
            quizBtn.setAttribute("aria-pressed", "true");
            listEl.style.display = "none";
            quizEl.style.display = "block";
            renderQuizCard();
        } else {
            quizBtn.classList.remove("is-active");
            quizBtn.setAttribute("aria-pressed", "false");
            browseBtn.classList.add("is-active");
            browseBtn.setAttribute("aria-pressed", "true");
            quizEl.style.display = "none";
            listEl.style.display = "block";
            stopQuizTimer();
        }
    }
}

const browseModeBtn = document.getElementById("browseModeBtn");
const quizModeBtn = document.getElementById("quizModeBtn");
if (browseModeBtn) {
    browseModeBtn.addEventListener("click", () => setInterviewMode("browse"));
}
if (quizModeBtn) {
    quizModeBtn.addEventListener("click", () => setInterviewMode("quiz"));
}

function renderInterviewQuestions(questions) {
    currentInterviewQuestions = questions;
    interviewQuestionList.replaceChildren();

    const modeToggle = document.getElementById("interviewModeToggle");
    if (modeToggle) {
        modeToggle.style.display = questions.length ? "inline-flex" : "none";
    }

    if (!questions.length) {
        interviewQuestionCount.textContent = "No questions found for this selection.";
        return;
    }

    interviewQuestionCount.textContent =
        `${questions.length} ${interviewTopic.selectedOptions[0].textContent} ${interviewLevel.value} questions. Think through each one before revealing the sample answer.`;

    const cards = document.createDocumentFragment();
    questions.forEach((item, index) => {
        const card = document.createElement("article");
        card.className = "interview-question-card";

        const meta = document.createElement("div");
        meta.className = "interview-question-meta";
        const topic = document.createElement("span");
        topic.textContent = item.topic_name;
        const level = document.createElement("span");
        level.className = `question-level level-${item.level}`;
        level.textContent = item.level;
        meta.append(topic, level);

        const heading = document.createElement("h3");
        heading.textContent = `${index + 1}. ${item.question}`;

        const answer = document.createElement("div");
        answer.className = "interview-answer";
        answer.hidden = true;
        const codeBlockPattern = /```([a-zA-Z0-9_-]*)\r?\n([\s\S]*?)```/g;
        let lastAnswerIndex = 0;
        let codeBlock;
        while ((codeBlock = codeBlockPattern.exec(item.answer)) !== null) {
            answer.appendChild(
                document.createTextNode(item.answer.slice(lastAnswerIndex, codeBlock.index))
            );
            const pre = document.createElement("pre");
            const code = document.createElement("code");
            code.className = codeBlock[1] ? `language-${codeBlock[1]}` : "";
            code.textContent = codeBlock[2].trimEnd();
            pre.appendChild(code);
            answer.appendChild(pre);
            lastAnswerIndex = codeBlockPattern.lastIndex;
        }
        if (lastAnswerIndex) {
            answer.appendChild(document.createTextNode(item.answer.slice(lastAnswerIndex)));
        } else {
            answer.textContent = item.answer;
        }

        const reveal = document.createElement("button");
        reveal.type = "button";
        reveal.className = "text-button reveal-answer";
        reveal.textContent = "Reveal sample answer";
        reveal.setAttribute("aria-expanded", "false");
        reveal.addEventListener("click", () => {
            answer.hidden = !answer.hidden;
            reveal.textContent = answer.hidden ? "Reveal sample answer" : "Hide sample answer";
            reveal.setAttribute("aria-expanded", String(!answer.hidden));
        });

        card.append(meta, heading, reveal, answer);
        cards.appendChild(card);
    });

    interviewQuestionList.replaceChildren(cards);
    if (currentInterviewMode === "quiz") {
        renderQuizCard();
    }
}

async function loadInterviewQuestions() {
    const submitButton = interviewQuestionForm.querySelector('button[type="submit"]');
    if (!interviewTopic.value || !interviewLevel.value) {
        interviewQuestionCount.textContent = "Select both a domain and a level to load questions.";
        interviewQuestionList.replaceChildren();
        return;
    }

    const requestId = ++interviewQuestionRequest;
    const selectedTopic = interviewTopic.value;
    const selectedLevel = interviewLevel.value;
    submitButton.disabled = true;
    submitButton.textContent = "Loading...";
    interviewQuestionCount.textContent = "Loading interview questions...";
    interviewQuestionList.replaceChildren();

    try {
        const params = new URLSearchParams({
            topic: selectedTopic,
            level: selectedLevel
        });
        const response = await fetch(`/api/interview-questions?${params}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Could not load interview questions.");
        }
        if (requestId !== interviewQuestionRequest) return;
        renderInterviewQuestions(data.questions);
    } catch (error) {
        if (requestId === interviewQuestionRequest) {
            interviewQuestionCount.textContent = error.message;
            interviewQuestionCount.classList.add("error");
        }
    } finally {
        if (requestId === interviewQuestionRequest) {
            submitButton.textContent = "Load selected questions";
            submitButton.disabled = !interviewTopic.value || !interviewLevel.value;
        }
    }
}

if (interviewQuestionForm) {
    interviewQuestionForm.addEventListener("submit", event => {
        event.preventDefault();
        interviewQuestionCount.classList.remove("error");
        loadInterviewQuestions();
    });
    const updateInterviewSelection = () => {
        interviewQuestionRequest += 1;
        interviewQuestionList.replaceChildren();
        interviewQuestionCount.textContent = "Load questions for your selected domain and level.";
        interviewQuestionCount.classList.remove("error");
        interviewQuestionForm.querySelector('button[type="submit"]').disabled =
            !interviewTopic.value || !interviewLevel.value;
    };
    interviewTopic.addEventListener("change", updateInterviewSelection);
    interviewLevel.addEventListener("change", updateInterviewSelection);
}

const dsaFilterForm = document.getElementById("dsa-filter-form");
const dsaTopic = document.getElementById("dsa-topic");
const dsaDifficulty = document.getElementById("dsa-difficulty");
const dsaProgress = document.getElementById("dsa-progress");
const dsaEncouragement = document.getElementById("dsa-encouragement");
const dsaProblemPanel = document.getElementById("dsa-problem-panel");
const dsaSolvedStorageKey = "devtrack-dsa-solved";
let dsaQuestions = [];
let solvedDsaQuestions = new Set();
let dsaProgressStorageAvailable = true;

function loadDsaProgress() {
    try {
        const savedIds = JSON.parse(localStorage.getItem(dsaSolvedStorageKey) || "[]");
        if (!Array.isArray(savedIds) || !savedIds.every(id => typeof id === "string")) {
            throw new Error("Saved DSA progress has an invalid format.");
        }
        const validIds = new Set(dsaQuestions.map(question => question.id));
        solvedDsaQuestions = new Set(savedIds.filter(id => validIds.has(id)));
    } catch (error) {
        dsaProgressStorageAvailable = false;
        console.error("Could not load saved DSA progress.", error);
    }
}

function updateDsaProgressMessage() {
    const savedMessage = dsaProgressStorageAvailable
        ? ""
        : " Progress could not be loaded from this browser.";
    dsaProgress.textContent =
        `${solvedDsaQuestions.size} of ${dsaQuestions.length} problems solved.${savedMessage}`;
}

function getFilteredDsaQuestions() {
    const levelOrder = { basic: 0, intermediate: 1, advanced: 2 };
    return dsaQuestions.filter(question =>
        (dsaTopic.value === "all" || question.topic === dsaTopic.value)
        && (dsaDifficulty.value === "all" || question.difficulty === dsaDifficulty.value)
    ).sort((first, second) =>
        levelOrder[first.difficulty] - levelOrder[second.difficulty]
    );
}

function updateDsaProblemList() {
    if (!dsaTopic.value || !dsaDifficulty.value) {
        dsaProblemPanel.textContent =
            "Choose a topic and difficulty, then load the matching problems.";
        return;
    }

    const questions = getFilteredDsaQuestions();
    dsaProblemPanel.replaceChildren();

    if (!questions.length) {
        dsaProblemPanel.textContent = "No problems match these filters.";
        return;
    }

    ["basic", "intermediate", "advanced"].forEach(level => {
        const levelQuestions = questions.filter(question => question.difficulty === level);
        if (!levelQuestions.length) return;

        const levelSection = document.createElement("section");
        levelSection.className = "dsa-level-section";
        const levelHeading = document.createElement("h3");
        levelHeading.textContent =
            `${level[0].toUpperCase()}${level.slice(1)} — ${levelQuestions.filter(question => solvedDsaQuestions.has(question.id)).length}/${levelQuestions.length} solved`;
        levelSection.appendChild(levelHeading);

        const questionList = document.createElement("div");
        questionList.className = "dsa-question-list";
        levelQuestions.forEach(question => {
            renderDsaProblem(question, questionList);
        });
        levelSection.appendChild(questionList);
        dsaProblemPanel.appendChild(levelSection);
    });
}

function renderDsaProblem(question, container) {
    const card = document.createElement("article");
    card.className = "dsa-question-card";
    const header = document.createElement("div");
    header.className = "dsa-problem-header";
    const heading = document.createElement("h3");
    heading.textContent = question.title;
    const difficulty = document.createElement("span");
    difficulty.className = `question-level level-${question.difficulty}`;
    difficulty.textContent = question.difficulty;
    header.append(heading, difficulty);

    const scenario = document.createElement("p");
    scenario.className = "dsa-scenario";
    scenario.textContent = question.scenario;

    const examples = document.createElement("div");
    examples.className = "dsa-examples";
    [
        ["Example input", question.input_example],
        ["Expected output", question.output_example]
    ].forEach(([label, value]) => {
        const example = document.createElement("div");
        const exampleHeading = document.createElement("h4");
        exampleHeading.textContent = label;
        const exampleCode = document.createElement("pre");
        exampleCode.textContent = value;
        example.append(exampleHeading, exampleCode);
        examples.appendChild(example);
    });

    const hint = document.createElement("details");
    hint.className = "dsa-reveal";
    const hintSummary = document.createElement("summary");
    hintSummary.textContent = "Show hint";
    const hintText = document.createElement("p");
    hintText.textContent = question.hint;
    hint.append(hintSummary, hintText);

    const editorDetails = document.createElement("details");
    editorDetails.className = "dsa-reveal dsa-editor";
    const editorSummary = document.createElement("summary");
    editorSummary.textContent = "Open Python editor";
    editorDetails.appendChild(editorSummary);

    const editorLabel = document.createElement("label");
    editorLabel.className = "dsa-editor-label";
    editorLabel.textContent = "Your Python solution";
    const editor = document.createElement("textarea");
    editor.className = "dsa-code-editor";
    editor.rows = 12;
    editor.spellcheck = false;
    editor.autocapitalize = "off";
    editor.autocomplete = "off";
    editor.setAttribute("aria-label", `Your Python solution for ${question.title}`);
    editor.placeholder = "Write your solution here, then test it locally with the example.";
    editor.readOnly = solvedDsaQuestions.has(question.id);

    const savedDraftMessage = document.createElement("p");
    savedDraftMessage.className = "dsa-draft-message";
    try {
        editor.value = localStorage.getItem(`devtrack-dsa-draft-${question.id}`) || "";
    } catch (error) {
        console.error("Could not load the saved DSA draft.", error);
        savedDraftMessage.textContent = "This browser does not allow saved drafts.";
    }
    editor.addEventListener("input", () => {
        try {
            localStorage.setItem(`devtrack-dsa-draft-${question.id}`, editor.value);
            savedDraftMessage.textContent = "Draft saved in this browser.";
        } catch (error) {
            console.error("Could not save the DSA draft.", error);
            savedDraftMessage.textContent = "Could not save the draft in this browser.";
        }
    });

    const actions = document.createElement("div");
    actions.className = "dsa-actions";
    const saveDraft = document.createElement("button");
    saveDraft.type = "button";
    saveDraft.className = "text-button";
    saveDraft.textContent = "Save draft";
    saveDraft.disabled = solvedDsaQuestions.has(question.id);
    saveDraft.addEventListener("click", () => {
        try {
            localStorage.setItem(`devtrack-dsa-draft-${question.id}`, editor.value);
            savedDraftMessage.textContent =
                "Nice effort! Draft saved. Keep going—you’re making progress.";
        } catch (error) {
            console.error("Could not save the DSA draft.", error);
            savedDraftMessage.textContent = "Could not save the draft in this browser.";
        }
    });

    const markSolved = document.createElement("button");
    markSolved.type = "button";
    markSolved.className = "primary-button";
    markSolved.textContent = solvedDsaQuestions.has(question.id)
        ? "Solved ✓"
        : "Mark as solved";
    markSolved.disabled = solvedDsaQuestions.has(question.id);
    markSolved.addEventListener("click", () => {
        solvedDsaQuestions.add(question.id);
        try {
            localStorage.setItem(`devtrack-dsa-draft-${question.id}`, editor.value);
            localStorage.setItem(
                dsaSolvedStorageKey,
                JSON.stringify([...solvedDsaQuestions])
            );
            dsaProgressStorageAvailable = true;
        } catch (error) {
            dsaProgressStorageAvailable = false;
            console.error("Could not save DSA progress.", error);
        }
        markSolved.textContent = "Solved ✓";
        markSolved.disabled = true;
        updateDsaProgressMessage();
        updateDsaProblemMessage(question);
        updateDsaProblemList();
    });
    actions.append(saveDraft, markSolved);

    const solution = document.createElement("details");
    solution.className = "dsa-reveal dsa-solution";
    const solutionSummary = document.createElement("summary");
    solutionSummary.textContent = "Reveal Python reference solution";
    const solutionCode = document.createElement("pre");
    solutionCode.textContent = question.solution;
    solution.append(solutionSummary, solutionCode);

    const note = document.createElement("p");
    note.className = "dsa-editor-note";
    note.textContent = "The editor saves drafts in this browser. Run your code locally; solutions are provided for comparison.";

    editorLabel.appendChild(editor);
    editorDetails.append(editorLabel, note);

    card.append(
        header,
        scenario,
        examples,
        hint,
        editorDetails,
        actions,
        savedDraftMessage,
        solution
    );
    container.appendChild(card);
}

function updateDsaProblemMessage(solvedQuestion = null) {
    if (solvedDsaQuestions.size === dsaQuestions.length) {
        dsaEncouragement.textContent =
            "Amazing—you’ve solved every problem! You should be proud of your progress.";
    } else if (solvedQuestion) {
        const article = solvedQuestion.difficulty === "basic" ? "a" : "an";
        dsaEncouragement.textContent =
            `Great job solving ${article} ${solvedQuestion.difficulty} problem! Keep going—you can choose any level next.`;
    } else {
        dsaEncouragement.textContent =
            "Choose a topic and difficulty to load only the matching practice problems.";
    }
}

async function loadDsaQuestions() {
    try {
        const response = await fetch("/api/dsa-questions");
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Could not load DSA problems.");
        }

        dsaQuestions = data.questions;
        loadDsaProgress();
        updateDsaProgressMessage();
        updateDsaProblemMessage();
        updateDsaProblemList();
    } catch (error) {
        dsaProgress.textContent = error.message;
        dsaProgress.classList.add("error");
        dsaProblemPanel.textContent = "Practice problems could not be loaded. Please try again later.";
    }
}

if (dsaFilterForm) {
    const updateDsaSelection = () => {
        dsaProblemPanel.textContent =
            "Press “Load selected problems” to show questions for your selection.";
        dsaEncouragement.textContent =
            "Only problems matching your selected topic and level will be shown.";
        dsaFilterForm.querySelector('button[type="submit"]').disabled =
            !dsaTopic.value || !dsaDifficulty.value;
    };
    dsaTopic.addEventListener("change", updateDsaSelection);
    dsaDifficulty.addEventListener("change", updateDsaSelection);
    dsaFilterForm.addEventListener("submit", event => {
        event.preventDefault();
        updateDsaProblemList();
    });
    loadDsaQuestions();
}
