"""One evidence-only recovery for a matched Nevada record painted under a loader."""
import secrets
import time



class LoadingFrame(ValueError):
    pass


def is_loading_frame(source, *, check_detail_panel=False):
    from PIL import Image, ImageChops

    small = source.convert("RGB")
    small.thumbnail((768, 768), Image.Resampling.BILINEAR)
    width, height = small.size
    if check_detail_panel and width >= 320 and height >= 220:
        # ORION can paint the record header and blue navigation while the
        # entire information panel is still white. Inspect first-view pixels.
        def region(left, top, right, bottom):
            return small.crop((int(width*left), int(height*top),
                               int(width*right), int(height*bottom)))
        body = region(.26, .30, .90, .72).convert('L')
        header = region(.04, .04, .94, .20).convert('L')
        menu = region(.01, .12, .24, .40)
        if (sum(body.histogram()[:200]) == 0 and sum(header.histogram()[:150]) >= 40
                and any(b > 115 and b-r > 65 and b-g > 20 for r,g,b in menu.getdata())):
            return True
    red, green, blue = small.split()
    brightest = ImageChops.lighter(red, ImageChops.lighter(green, blue))
    if sum(brightest.histogram()[:130]) > width * height * 0.00015:
        return False
    center = small.crop((int(width*.43), int(height*.39), int(width*.57), int(height*.61)))
    values = center.tobytes()
    blue_pixels = sum(b > 120 and b-r > 75 and b-g > 45
                      for r, g, b in zip(values[::3], values[1::3], values[2::3]))
    return blue_pixels >= max(8, width * height * .00005)


def prepare(master, record, *, selected=None, result=None):
    """Take a single second look while the connector still owns the selected detail."""
    item = selected or record["completed"][-1]
    query = item["query"]
    identifier = query.get("identifier")
    if (query.get("operation") != "detail" or record.get("nv_image_recovery_attempted")
            or identifier not in record.get("nv_loading_frames", ())
            or record["expires"] - time.time() < 12
            or any(ref.get("identifier") == identifier and ref.get("operation") == "detail"
                   for ref in record.get("source_snapshots", ()))):
        return None
    query_id = secrets.token_urlsafe(18)
    signed = {**record, "nv_pixel_receipt": {"query_id": query_id, "identifier": identifier},
              "nv_image_recovery_attempted": True}
    if result is not None:
        signed["nv_settled_result"] = result
    try:
        token = master.ny_connector_pack(signed)
    except ValueError:
        return None
    remaining = record["expires"] - time.time()
    if remaining < 10:
        return None
    return {"phase": "search", "query": query, "query_id": query_id,
            "nv_followup_ms": min(14000, int(remaining * 1000)) if result is not None else 5500, "lookup_remaining_ms": int(remaining*1000),
            "expires_in": int(remaining), "check_token": token}


def recover_selected(master, record, result):
    """Retry the original image only after every search and selection is settled."""
    if record.get("nv_image_recovery_attempted") or not record.get("nv_loading_frames"):
        return None
    identifier = result.get("matched_registry_identifier")
    if not identifier and record.get("_nv_scope_detail"):
        identifier = record["_nv_scope_detail"][0]
    if not identifier:
        candidates = (result.get("identity_review") or {}).get("candidates") or []
        if len(candidates) == 1:
            identifier = candidates[0].get("identifier")
    if not identifier or identifier not in record["nv_loading_frames"]:
        return None
    item = next((entry for entry in reversed(record["completed"])
                 if entry["query"].get("operation") == "detail"
                 and entry["query"].get("identifier") == identifier), None)
    if not item:
        return None
    return prepare(master, record, selected=item, result=result)


def finish(master, record, payload, action):
    from deployment.state_snapshots import connector_archive

    receipt = record["nv_pixel_receipt"]
    item = next((entry for entry in reversed(record["completed"])
                 if entry["query"].get("operation") == "detail"
                 and entry["query"].get("identifier") == receipt["identifier"]), None)
    if item is None:
        return False
    if (payload.get("query_id") != receipt["query_id"]
            or item["query"].get("identifier") != receipt["identifier"]):
        return False
    if action == "advance":
        try:
            evidence = master.final_four_clean_evidence(payload.get("evidence"), item["query"])
        except (TypeError, KeyError, ValueError):
            evidence = None
        if evidence == item["evidence"] and evidence is not None:
            connector_archive(record, payload, item["query"], evidence)
    del record["nv_pixel_receipt"]
    return True
