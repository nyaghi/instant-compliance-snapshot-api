"""One evidence-only recovery for a matched Nevada record painted under a loader."""
import secrets
import time



class LoadingFrame(ValueError):
    pass


def is_loading_frame(source):
    from PIL import Image, ImageChops

    small = source.convert("RGB")
    small.thumbnail((768, 768), Image.Resampling.BILINEAR)
    width, height = small.size
    red, green, blue = small.split()
    brightest = ImageChops.lighter(red, ImageChops.lighter(green, blue))
    if sum(brightest.histogram()[:130]) > width * height * 0.00015:
        return False
    center = small.crop((int(width*.43), int(height*.39), int(width*.57), int(height*.61)))
    values = center.tobytes()
    blue_pixels = sum(b > 120 and b-r > 75 and b-g > 45
                      for r, g, b in zip(values[::3], values[1::3], values[2::3]))
    return blue_pixels >= max(8, width * height * .00005)


def prepare(master, record, response):
    """Recapture by exact state ID only after ordinary matching has finished."""
    result = response["result"]
    identifier = result.get("matched_registry_identifier")
    if (result.get("evidence_url") or result.get("identity_review") or
            record["expires"] - time.time() < 12 or
            identifier not in record.get("nv_loading_frames", ())):
        return response
    selected = next((item for item in record["completed"]
                     if item["query"].get("operation") == "detail"
                     and item["query"].get("identifier") == identifier), None)
    if not selected:
        return response
    query_id = secrets.token_urlsafe(18)
    signed = {**record, "nv_pixel_receipt": {"result": result, "query_id": query_id,
                                          "identifier": identifier}}
    try:
        token = master.ny_connector_pack(signed)
    except ValueError:
        return response
    remaining = record["expires"] - time.time()
    if remaining < 10:
        return response
    return {"phase": "search", "query": selected["query"], "query_id": query_id,
            "nv_followup_ms": 5500, "lookup_remaining_ms": int(remaining*1000),
            "expires_in": int(remaining), "check_token": token}


def finish(master, record, payload, action):
    from deployment.state_snapshots import attach_links, connector_archive

    receipt = record["nv_pixel_receipt"]
    if payload.get("query_id") != receipt["query_id"]:
        return 409, {"error": "The capture belongs to another registry query."}
    result = receipt["result"]
    if action == "advance":
        item = next(i for i in record["completed"] if i["query"].get("operation") == "detail"
                    and i["query"].get("identifier") == receipt["identifier"])
        try:
            evidence = master.final_four_clean_evidence(payload.get("evidence"), item["query"])
        except (TypeError, KeyError, ValueError):
            evidence = None
        if evidence == item["evidence"] and evidence is not None:
            connector_archive(record, payload, item["query"], evidence)
            linked = attach_links(result, record.get("source_snapshots", []))
            if linked.get("evidence_url"):
                result = linked
    return 200, {"phase": "complete", "result": result}
