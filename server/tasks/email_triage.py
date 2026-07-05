"""Email triage: archive every email from a target sender, star one target
email. Tests list scanning, precision (extra archives fail), and toggles."""

from __future__ import annotations

from typing import Any

from ..seeding import PREVIEWS, TOPICS, person, rng

N_EMAILS = 12
N_SENDERS = 6
TARGET_SENDER_COUNT = 3


class EmailTriage:
    id = "email-triage"
    title = "Inbox"
    template = "email_triage.html"

    def generate(self, seed: int) -> dict[str, Any]:
        r = rng(self.id, seed)
        senders = []
        while len(senders) < N_SENDERS:
            p = person(r)
            if p["name"] not in [s["name"] for s in senders]:
                senders.append(p)
        target_sender = senders[0]

        # sender assignment: target sender appears exactly TARGET_SENDER_COUNT times
        assignment = [0] * TARGET_SENDER_COUNT + [
            r.randrange(1, N_SENDERS) for _ in range(N_EMAILS - TARGET_SENDER_COUNT)
        ]
        r.shuffle(assignment)

        topics = r.sample(TOPICS, N_EMAILS)  # distinct topics => unambiguous keyword
        emails = [
            {
                "id": i,
                "sender": senders[assignment[i]]["name"],
                "subject": topics[i],
                "preview": r.choice(PREVIEWS),
                "archived": False,
                "starred": False,
            }
            for i in range(N_EMAILS)
        ]

        # star target: an email NOT from the target sender, so goals never collide
        star_candidates = [e for e in emails if e["sender"] != target_sender["name"]]
        star_email = r.choice(star_candidates)

        return {
            "emails": emails,
            "target_sender": target_sender["name"],
            "target_keyword": star_email["subject"],
            "star_target_id": star_email["id"],
        }

    def instruction(self, state: dict[str, Any]) -> str:
        return (
            f"In the inbox, archive every email from {state['target_sender']} "
            f"and star the email with the subject “{state['target_keyword']}”. "
            "Do not archive or star anything else."
        )

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"emails": [e for e in state["emails"] if not e["archived"]]}

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        op, email_id = payload.get("op"), payload.get("id")
        email = next((e for e in state["emails"] if e["id"] == email_id), None)
        if email is None:
            return {"ok": False, "error": "no such email"}
        if op == "archive":
            email["archived"] = True
            return {"ok": True}
        if op == "star":
            email["starred"] = not email["starred"]
            return {"ok": True, "starred": email["starred"]}
        return {"ok": False, "error": f"unknown op '{op}'"}

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        target = state["target_sender"]
        archived = {e["id"] for e in state["emails"] if e["archived"]}
        should_archive = {e["id"] for e in state["emails"] if e["sender"] == target}
        starred = {e["id"] for e in state["emails"] if e["starred"]}
        return {
            "archived_all_from_target": should_archive <= archived,
            "no_extra_archived": archived <= should_archive,
            "starred_target_only": starred == {state["star_target_id"]},
        }
