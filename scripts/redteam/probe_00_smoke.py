"""Smoke test: verifies endpoint, response shape (noul/choice/score), model id reported,
usage fields, and which model names are accepted (jev-1.13, jev-1.13.0, jev-latest).
Method: 1 request per model name with one question of each primitive; plus GET /v1/models."""
import asyncio, json
import httpx
from jevclient import Jev, save, _KEY, _bump

Q = {
 "n": {"type": "noul", "instructions": "Does this convey urgency?"},
 "c": {"type": "choice", "instructions": "Which team should handle this?",
       "criteria": {"billing": "Payments, invoicing, refunds", "technical": "Bugs, outages", "sales": "Pricing"}},
 "s": {"type": "score", "instructions": "How frustrated is the customer?", "criteria": ["Calm", "Frustrated", "Very angry"]},
}
async def main():
    j = Jev()
    out = {}
    for m in ["jev-1.13.0", "jev-1.13", "jev-latest"]:
        out[m] = await j.ask("Help! My payouts have been failing for 3 days.", Q, model=m)
    async with httpx.AsyncClient() as c:
        r = await c.get("https://api.typesafe.ai/v1/models", headers={"Authorization": f"Bearer {_KEY}"}); _bump()
        out["models_list"] = {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}
        # capture response headers once (non-secret)
        r = await c.post("https://api.typesafe.ai/v1/systemone", headers={"Authorization": f"Bearer {_KEY}"},
                         json={"model": "jev-1.13.0", "state": "hi", "questions": {"n": Q["n"]}}); _bump()
        out["headers"] = dict(r.headers)
    await j.aclose()
    save("p00_smoke", out)
    print(json.dumps(out, indent=1)[:6000])
asyncio.run(main())
