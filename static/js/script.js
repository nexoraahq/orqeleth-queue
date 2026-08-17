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
// LOAD FOUNDING 100 LEADERBOARD
// ==========================================

async function loadLeaderboard() {

    const leaderboard =
        document.getElementById("leaderboard");

    if (!leaderboard) {
        return;
    }

    try {

        const response =
            await fetch("/api/leaderboard");

        if (!response.ok) {
            throw new Error(
                "Leaderboard API returned " +
                response.status
            );
        }

        const data =
            await response.json();

        if (
            !data.success ||
            !Array.isArray(data.leaderboard)
        ) {
            throw new Error(
                "Invalid leaderboard data"
            );
        }


        // --------------------------------------
        // NO VERIFIED MEMBERS
        // --------------------------------------

        if (data.leaderboard.length === 0) {

            leaderboard.innerHTML = `
                <div style="
                    width:100%;
                    text-align:center;
                    padding:70px 20px;
                    color:#85808f;
                    font-size:16px;
                    line-height:1.8;
                ">
                    The race is live.
                    <br>
                    The leaderboard will populate as verified members join.
                </div>
            `;

            return;
        }


        // --------------------------------------
        // LEADERBOARD DATA
        // --------------------------------------

        leaderboard.innerHTML = `
            <div style="
                width:100%;
            ">

                ${data.leaderboard.map(function(user) {

                    const rank =
                        Number(user.rank || 0);

                    const name =
                        escapeHtml(
                            user.name || "ORQELETH Member"
                        );

                    const referrals =
                        Number(
                            user.verified_referrals || 0
                        ).toLocaleString();

                    return `
                        <div style="
                            display:grid;
                            grid-template-columns:
                                140px
                                minmax(0, 1fr)
                                260px;
                            align-items:center;
                            min-height:72px;
                            padding:0 32px;
                            border-bottom:
                                1px solid rgba(255,255,255,0.055);
                        ">

                            <div style="
                                color:#c084ff;
                                font-weight:800;
                                font-size:16px;
                            ">
                                #${rank}
                            </div>

                            <div style="
                                color:#f5f2fa;
                                font-weight:700;
                                font-size:16px;
                                overflow:hidden;
                                text-overflow:ellipsis;
                                white-space:nowrap;
                            ">
                                ${name}
                            </div>

                            <div style="
                                color:#c084ff;
                                font-weight:800;
                                font-size:16px;
                                text-align:right;
                            ">
                                ${referrals}
                            </div>

                        </div>
                    `;

                }).join("")}

            </div>
        `;


    } catch (error) {

        console.error(
            "Leaderboard loading error:",
            error
        );

        leaderboard.innerHTML = `
            <div style="
                width:100%;
                text-align:center;
                padding:70px 20px;
                color:#85808f;
                font-size:16px;
                line-height:1.8;
            ">
                Unable to load the leaderboard.
                <br>
                Please refresh and try again.
            </div>
        `;
    }
}


// ==========================================
// SAFE HTML ESCAPE
// ==========================================

function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent =
        value == null
            ? ""
            : String(value);

    return div.innerHTML;
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

                loadLeaderboard();


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

        loadLeaderboard();

    }
);