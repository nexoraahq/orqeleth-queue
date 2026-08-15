// ==========================================
// ORQELETH QUEUE — FRONTEND
// ==========================================


// ==========================================
// MODAL
// ==========================================

function openJoinModal() {
    document
        .getElementById("joinModal")
        .classList.add("active");
}


function closeJoinModal() {
    document
        .getElementById("joinModal")
        .classList.remove("active");
}


// ==========================================
// LEADERBOARD SCROLL
// ==========================================

function scrollToLeaderboard() {

    const leaderboard =
        document.getElementById("leaderboard");

    if (leaderboard) {
        leaderboard.scrollIntoView({
            behavior: "smooth"
        });
    }
}


// ==========================================
// LOAD CAMPAIGN COUNT
// ==========================================

async function loadCampaign() {

    try {

        const response =
            await fetch("/api/campaign");

        const data =
            await response.json();

        const countElement =
            document.getElementById("queueCount");

        const progressElement =
            document.getElementById("progressBar");

        if (countElement) {

            countElement.textContent =
                data.verified_registrations
                    .toLocaleString();
        }

        if (progressElement) {

            const percentage =
                (
                    data.verified_registrations /
                    data.capacity
                ) * 100;

            progressElement.style.width =
                Math.min(percentage, 100) + "%";
        }

    } catch (error) {

        console.error(
            "Campaign loading error:",
            error
        );
    }
}


// ==========================================
// REGISTRATION
// ==========================================

const joinForm =
    document.getElementById("joinForm");


if (joinForm) {

    joinForm.addEventListener(
        "submit",
        async function(event) {

            event.preventDefault();

            const name =
                document
                    .getElementById("name")
                    .value
                    .trim();

            const email =
                document
                    .getElementById("email")
                    .value
                    .trim();

            const username =
                document
                    .getElementById("username")
                    .value
                    .trim();


            const submitButton =
                joinForm.querySelector(
                    "button[type='submit']"
                );

            const message =
                document.getElementById(
                    "formMessage"
                );


            submitButton.disabled = true;

            submitButton.innerHTML =
                "JOINING...";


            message.textContent = "";


            try {

                const response =
                    await fetch(
                        "/api/register",
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body: JSON.stringify({
                                name: name,
                                email: email,
                                username: username
                            })
                        }
                    );


                const data =
                    await response.json();


                if (!response.ok) {

                    message.textContent =
                        data.message ||
                        "Something went wrong.";

                    submitButton.disabled =
                        false;

                    submitButton.innerHTML =
                        'JOIN THE QUEUE <span>→</span>';

                    return;
                }


                message.innerHTML = `
    <strong>
        You're in the queue.
    </strong>

    <br><br>

    Your queue position:
    <strong>
        #${data.queue_position.toLocaleString()}
    </strong>

    <br><br>

    <a
        href="${data.verification_url}"
        target="_blank"
        style="
            color:#b875ff;
            font-weight:700;
        "
    >
        VERIFY EMAIL →
    </a>
`;


                joinForm.reset();

                submitButton.innerHTML =
                    "REGISTERED ✓";


                loadCampaign();


            } catch (error) {

                console.error(error);

                message.textContent =
                    "Unable to connect to the server.";

                submitButton.disabled =
                    false;

                submitButton.innerHTML =
                    'JOIN THE QUEUE <span>→</span>';
            }

        }
    );
}


// ==========================================
// INITIAL LOAD
// ==========================================

document.addEventListener(
    "DOMContentLoaded",
    function() {

        loadCampaign();

    }
);