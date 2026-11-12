const authForm = document.getElementById("auth-form");

if (authForm) {
    const authName = document.getElementById("auth-name");
    const authPassword = document.getElementById("auth-password");
    const authSubmit = document.getElementById("auth-submit");
    const authMessage = document.getElementById("auth-message");
    const authSwitch = document.getElementById("auth-switch");
    const authSwitchPrompt = document.getElementById("auth-switch-prompt");
    let registering = false;

    authPassword.minLength = 1;
    authSwitch.addEventListener("click", () => {
        registering = !registering;
        authSubmit.textContent = registering ? "Create account" : "Sign in";
        authPassword.autocomplete = registering ? "new-password" : "current-password";
        authPassword.minLength = registering ? 8 : 1;
        authSwitchPrompt.textContent = registering ? "Already have an account?" : "New here?";
        authSwitch.textContent = registering ? "Sign in" : "Create an account";
        authMessage.textContent = "";
    });

    authForm.addEventListener("submit", async event => {
        event.preventDefault();

        const name = authName.value.trim();
        const password = authPassword.value;

        if (!name || !password) {
            authMessage.textContent = "Please enter both your name and password.";
            authMessage.classList.add("error");
            return;
        }

        authSubmit.disabled = true;
        authMessage.textContent = registering ? "Creating your account..." : "Signing in...";
        authMessage.classList.remove("error");

        try {
            const response = await fetch(`/api/auth/${registering ? "register" : "login"}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name,
                    password
                })
            });
            const result = await response.json();
            if (!response.ok) {
                throw new Error(result.error || "Could not authenticate.");
            }
            window.location.assign(result.redirect || "/dashboard");
        } catch (error) {
            authMessage.textContent = error.message;
            authMessage.classList.add("error");
        } finally {
            authSubmit.disabled = false;
        }
    });
}
