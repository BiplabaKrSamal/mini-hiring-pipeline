def add(client, name="Priya Sharma"):
    return client.post("/api/candidates", json={"name": name})


def move(client, cid, to, note=""):
    return client.post(f"/api/candidates/{cid}/moves", json={"to": to, "note": note})


def test_the_page_is_served(client):
    assert "Hiring pipeline" in client.get("/").text
    assert client.get("/app.js").status_code == 200 and client.get("/styles.css").status_code == 200


def test_add_and_list(client):
    r = add(client)
    assert r.status_code == 201 and r.json()["stage"] == "applied" and r.json()["next"] == ["screening", "rejected"]
    listing = client.get("/api/candidates").json()
    assert [s["id"] for s in listing["stages"]] == ["applied", "screening", "interview", "offer", "hired", "rejected"]
    assert [c["name"] for c in listing["candidates"]] == ["Priya Sharma"]


def test_history_and_time_in_stage(client, clock):
    cid = add(client).json()["id"]
    clock.advance(days=3)
    move(client, cid, "screening", "Phone screen booked")
    clock.advance(days=9, hours=4)
    body = client.get(f"/api/candidates/{cid}").json()
    assert body["in_stage_seconds"] == 9 * 86400 + 4 * 3600
    assert [(h["from"], h["to"], h["note"]) for h in body["history"]] == [(None, "applied", ""), ("applied", "screening", "Phone screen booked")]
    assert body["history"][0]["seconds_in_stage"] == 3 * 86400


def test_the_rules_hold_over_http(client):
    cid = add(client).json()["id"]
    skip = move(client, cid, "offer")
    assert skip.status_code == 409 and "skip" in skip.json()["error"]
    for stage in ("screening", "interview", "offer", "hired"):
        assert move(client, cid, stage).status_code == 200
    assert move(client, cid, "rejected").status_code == 409
    assert client.get(f"/api/candidates/{cid}").json()["next"] == []


def test_errors_are_json_with_a_readable_message(client):
    assert client.get("/api/candidates/999").status_code == 404
    assert add(client, "   ").status_code == 422
    r = move(client, add(client).json()["id"], "banana")
    assert r.status_code == 422 and "applied" in r.json()["error"]


def test_search_returns_the_reading_the_results_and_the_reasons(client, clock):
    cid = add(client).json()["id"]
    move(client, cid, "screening")
    clock.advance(days=9)
    body = client.get("/api/search", params={"q": "stuck in screening for more than a week", "tz": "Asia/Kolkata"}).json()
    assert [r["name"] for r in body["results"]] == ["Priya Sharma"] and body["results"][0]["in_stage_seconds"] == 9 * 86400
    assert [i["text"] for i in body["interpretation"]] == ["In Screening", "Stuck for more than a week"]
    assert client.get("/api/search", params={"q": "sharam"}).json()["results"][0]["reasons"] == ["\u201csharam\u201d is close to Sharma (typo)"]


def test_search_explains_instead_of_returning_a_blank(client):
    add(client)
    body = client.get("/api/search", params={"q": "stuck in hired"}).json()
    assert body["results"] == [] and body["empty_reason"] and any(n["level"] == "error" for n in body["notices"])
    assert client.get("/api/search", params={"q": ""}).json()["mode"] == "browse"
    assert client.get("/api/search", params={"q": "x", "tz": "Mars/Base"}).status_code == 422


def test_hostile_names_are_stored_as_typed_for_the_page_to_escape(client):
    name = "<script>alert(1)</script> Test"
    assert add(client, name).json()["name"] == name
