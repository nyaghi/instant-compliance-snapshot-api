import base64
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw
from deployment import nv_snapshot_quality as quality, state_snapshots as snapshots


def image_data(loading):
    bitmap = Image.new("RGB", (512, 400), "white")
    draw = ImageDraw.Draw(bitmap)
    draw.text((50, 40), "Nevada public detail", fill="silver" if loading else "black")
    if loading:
        draw.ellipse((242, 186, 270, 214), outline="blue", width=4)
    buf = io.BytesIO()
    bitmap.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


class PublicationTest(unittest.TestCase):
    def test_original_status_and_bound_recovery_across_70_organizations(self):
        roster = json.loads((Path(__file__).parent/"fixtures/gate55/LOCAL-70.json").read_text())
        self.assertEqual(70, len({org["ein"] for org in roster}))
        clean, faded = image_data(False), image_data(True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(snapshots, "STORE", snapshots.SQLiteStore(Path(tmp)/"test.db")):
            for i, org in enumerate(roster):
                with self.subTest(ein=org["ein"]):
                    ident = f"NV{100000+i}"
                    url = "https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=40657bad-c090-4307-82e8-d23921cababc"
                    q = dict(state="NV", operation="detail", identifier=ident)
                    evidence = {"fields":{"Entity Name":org["name"], "NV Business ID":ident}}
                    result = dict(state="NV", ein=org["ein"], matched_registry_name=org["name"], matched_registry_identifier=ident, status="Delinquent")
                    rec = dict(state="NV", ein=org["ein"], organization_name=org["name"], issued=time.time()-5, expires=time.time()+60, completed=[dict(query=q, evidence=evidence)])
                    response = dict(phase="complete", result=result)
                    snap = dict(query=q, public_text=org["name"]+" "+ident, source_url=url, captured_at=time.time(), image=faded)
                    reply = dict(query_id="old", state_snapshot=snap, evidence=evidence)
                    snapshots.connector_archive(rec, reply, q, evidence)
                    self.assertEqual([ident], rec["nv_loading_frames"])
                    self.assertFalse(rec.get("source_snapshots"))
                    packed = {}
                    def pack(record):
                        packed.update(record)
                        return "test-token"
                    master = SimpleNamespace(ny_connector_pack=pack, final_four_clean_evidence=lambda payload,query:payload)
                    self.assertIs(quality.prepare(master,dict(rec,expires=time.time()+2),response),response)
                    self.assertEqual(quality.prepare(master,rec,dict(phase="complete",result=dict(result,evidence_url="original")))["result"]["evidence_url"],"original")
                    request=quality.prepare(master,rec,response)
                    self.assertEqual(q, request["query"])
                    self.assertEqual(5500, request["nv_followup_ms"])
                    self.assertEqual(409,quality.finish(master,packed,reply,"advance")[0])
                    reply["query_id"]=request["query_id"]
                    for action,data in [("fail",reply),("advance",dict(reply,evidence={})),("advance",reply)]:
                        self.assertEqual((200,response),quality.finish(master,packed,data,action))
                    snap["image"]=clean
                    _, complete=quality.finish(master,packed,reply,"advance")
                    self.assertEqual(result["status"], complete["result"]["status"])
                    self.assertTrue(complete["result"]["evidence_url"].startswith("/state-snapshots/"))

