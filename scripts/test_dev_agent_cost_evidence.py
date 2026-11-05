"""Offline adversarial tests for authenticated costs and settlement transport."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import copy
import unittest
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

from dev_agent_accounting import finalize, reserve_and_sign, consume
from dev_agent_cost_evidence import Producer, collect_cost, sign_cost, ingest_cost
from dev_agent_signed_evidence import sign, verify

NOW = int(datetime(2026,11,4,18,tzinfo=timezone.utc).timestamp())
START = NOW-18*3600
PRODUCER = Producer("mpeng98-source/Restaurant-AI-central",
                    ".github/workflows/chubby-dev-agent-utc-cost-collection.yml","a"*40,100,1)
KEY = b"offline-cost-test-key-never-production!!"
BINDING = dict(run_id=101,issue_number=39,head_sha="b"*40,project_id="proj_acceptance_offline")


def page(value="1.25"):
    return {"data":[{"start_time":START,"end_time":START+86400,"results":[
        {"project_id":BINDING["project_id"],"amount":{"currency":"usd","value":value}}]}],
        "has_more":False,"next_page":None}


def report():
    return collect_cost(lambda _:page(),project_id=BINDING["project_id"],utc_day="2026-11-04",now=NOW)


class CostEvidenceTests(unittest.TestCase):
    def test_project_filter_utc_window_and_precision_rounds_up(self):
        urls=[]
        def fetch(url):
            urls.append(url)
            return page("0.0000001")
        r=collect_cost(fetch,project_id=BINDING["project_id"],utc_day="2026-11-04",now=NOW)
        self.assertEqual(r["reported_usd"],"0.000001")
        query=parse_qs(urlparse(urls[0]).query)
        self.assertEqual(query["project_ids"],[BINDING["project_id"]])
        self.assertEqual(query["start_time"],[str(START)])
        self.assertEqual(query["end_time"],[str(NOW)])

    def test_empty_response_is_not_zero_proof(self):
        p=page();p["data"][0]["results"]=[]
        with self.assertRaises(ValueError):
            collect_cost(lambda _:p,project_id=BINDING["project_id"],utc_day="2026-11-04",now=NOW)

    def test_bad_api_responses(self):
        cases=[]
        for value in ("NaN","Infinity","-1",None): cases.append(page(value))
        for key,value in (("project_id","proj_other"),("amount",{})):
            p=page();p["data"][0]["results"][0][key]=value;cases.append(p)
        p=page();p.pop("has_more");cases.append(p)
        p=page();p["has_more"]=True;cases.append(p)
        p=page();p["next_page"]="unexpected";cases.append(p)
        p=page();p["data"][0]["start_time"]-=86400;cases.append(p)
        for p in cases:
            with self.subTest(p=p),self.assertRaises(ValueError):
                collect_cost(lambda _:p,project_id=BINDING["project_id"],utc_day="2026-11-04",now=NOW)

    def test_duplicate_paginated_bucket_denied(self):
        p=page();p.update(has_more=True,next_page="repeat")
        with self.assertRaises(ValueError):
            collect_cost(lambda _:p,project_id=BINDING["project_id"],utc_day="2026-11-04",now=NOW)

    def ingest(self,e,**kw):
        return ingest_cost(self.conn,e,KEY,producer=PRODUCER,
                           project_id=BINDING["project_id"],now=kw.get("now",NOW))

    def setUp(self):
        self.conn=MagicMock();self.conn.info.transaction_status=0

    def test_signed_report_reaches_sql_with_digest(self):
        digest=self.ingest(sign_cost(report(),KEY,producer=PRODUCER,now=NOW))
        self.assertEqual(len(digest),64)
        self.conn.execute.assert_called_once()

    def test_tampering_wrong_key_and_unsigned_rejected_before_sql(self):
        e=sign_cost(report(),KEY,producer=PRODUCER,now=NOW)
        bad=copy.deepcopy(e);bad["payload"]["report"]["reported_usd"]="0"
        wrong=sign_cost(report(),b"another-test-cost-key-long-enough!!!",producer=PRODUCER,now=NOW)
        for item in (bad,wrong,report(),{}):
            with self.subTest(item=item),self.assertRaises(ValueError):self.ingest(item)
        self.conn.execute.assert_not_called()

    def test_wrong_provenance_rejected(self):
        for p in (replace(PRODUCER,repository="attacker/repo"),replace(PRODUCER,sha="c"*40),
                  replace(PRODUCER,workflow=".github/workflows/untrusted.yml"),
                  replace(PRODUCER,run_id=999),replace(PRODUCER,attempt=2)):
            with self.subTest(p=p),self.assertRaises(ValueError):
                self.ingest(sign_cost(report(),KEY,producer=p,now=NOW))
        self.conn.execute.assert_not_called()

    def test_expired_future_and_stale_observation_rejected(self):
        for issued,when in ((NOW,NOW+300),(NOW+1,NOW),(NOW-301,NOW)):
            with self.subTest(issued=issued),self.assertRaises(ValueError):
                self.ingest(sign_cost(report(),KEY,producer=PRODUCER,now=issued),now=when)
        self.conn.execute.assert_not_called()

    def test_invalid_report_signed_by_collector_still_rejected(self):
        for key,value in (("project_id","proj_other"),("reported_usd","NaN"),
                          ("reported_usd","0.0000001"),("window_start",START+1),
                          ("window_end",START+86401),("observed_at",True),
                          ("source","uploaded"),("project_rows",0)):
            r=report();r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.ingest(sign_cost(r,KEY,producer=PRODUCER,now=NOW))
        self.conn.execute.assert_not_called()

    def test_no_result_can_escape_outer_uncommitted_transaction(self):
        self.conn.info.transaction_status=2
        with self.assertRaises(ValueError):
            self.ingest(sign_cost(report(),KEY,producer=PRODUCER,now=NOW))
        self.conn.execute.assert_not_called()


class PermitAndSettlementProofTests(unittest.TestCase):
    def test_weak_verification_key_and_boolean_bindings_denied(self):
        body={"kind":"codex_permit",**BINDING,"issued_at":NOW,"expires_at":NOW+120,"nonce":"a"*32}
        for key,changes in ((b"weak",{}),(KEY,{"run_id":True}),(KEY,{"issued_at":True})):
            e=sign({**body,**changes},KEY)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                verify(e,key,kind="codex_permit",now=NOW,**BINDING)

    def test_reserve_missing_key_fails_before_sql(self):
        db=MagicMock()
        with self.assertRaises(ValueError):
            reserve_and_sign(db,b"",cost_digest="a"*64,now=NOW,**BINDING)
        db.execute.assert_not_called()

    def test_settlement_needs_separate_review_and_correct_binding(self):
        base={"kind":"settlement_review_v1","producer":asdict(PRODUCER),
              "issued_at":NOW,"expires_at":NOW+120,"binding":BINDING,
              "decision":"settled","cost_digest":"a"*64,
              "finished_at":NOW-86401,"review_reference":"review/39"}
        cases=[base,{**base,"billing_finality_reviewed":False},
               {**base,"billing_finality_reviewed":True,"binding":{**BINDING,"head_sha":"f"*40}},
               {**base,"billing_finality_reviewed":True,"finished_at":NOW+1}]
        db=MagicMock()
        for body in cases:
            with self.subTest(body=body),self.assertRaises(ValueError):
                finalize(db,sign(body,KEY),KEY,producer=PRODUCER,now=NOW,**BINDING)
        db.execute.assert_not_called()

    def test_permit_tamper_expiry_rejected_before_sql(self):
        db=MagicMock()
        base={"kind":"codex_permit",**BINDING,"issued_at":NOW,"expires_at":NOW+120,"nonce":"a"*32}
        for changes in ({"head_sha":"f"*40},{"expires_at":NOW},{"project_id":"proj_other"}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                consume(db,sign({**base,**changes},KEY),KEY,now=NOW,**BINDING)
        db.execute.assert_not_called()


if __name__=="__main__":
    unittest.main()
