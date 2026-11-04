"""Adversarial trusted-output admission and publisher boundary tests."""
from dataclasses import asdict, replace
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from dev_agent_execution_gate import Context, REPOSITORY, WORKFLOW, select, recheck, admit, execute_simulated, reserve, authorize
from dev_agent_proposal import validate, publish

NOW=1800000000
CTX=Context(REPOSITORY,WORKFLOW,"refs/heads/main","a"*40,100,1,50,"proj_acceptance_gate")


def snapshot():
    return {"issues":[{"number":50,"title":"Clarify inventory count example","body":"Improve the worked count example in docs/sprint-2b-counting.md.",
                       "state":"open","labels":["agent-approved","agent-safe"]}],"pull_requests":[]}


def receipt(plan):
    return {"allowed":True,"context":asdict(CTX),"task_digest":plan["task_digest"],"authorized_at":NOW,"admit_before":NOW+300}


class ExecutionGateTests(unittest.TestCase):
    def test_valid_plan_admits_exactly_expected_task(self):
        plan=select(snapshot(),CTX);call=MagicMock()
        execute_simulated(receipt(plan),plan,call,ctx=CTX,now=NOW)
        call.assert_called_once_with(plan["task"])

    def test_missing_false_expired_future_or_wrong_context_never_executes(self):
        plan=select(snapshot(),CTX);good=receipt(plan)
        cases=[None,{}, {**good,"allowed":False},{**good,"allowed":"true"},
               {**good,"admit_before":NOW},{**good,"authorized_at":NOW+1},
               {**good,"context":{**good["context"],"attempt":2}},
               {**good,"context":{**good["context"],"head_sha":"b"*40}},
               {**good,"task_digest":"f"*64},{**good,"extra":"artifact"}]
        callback=MagicMock()
        for value in cases:
            with self.subTest(value=value),self.assertRaises(ValueError):
                execute_simulated(value,plan,callback,ctx=CTX,now=NOW)
        callback.assert_not_called()

    def test_restarted_attempt_and_non_main_rejected(self):
        plan=select(snapshot(),CTX)
        for ctx in (replace(CTX,attempt=2),replace(CTX,ref="refs/heads/topic"),replace(CTX,repository="attacker/repo"),replace(CTX,attempt=True)):
            with self.subTest(ctx=ctx),self.assertRaises(ValueError):admit(receipt(plan),plan,ctx=ctx,now=NOW)

    def test_revoked_approval_edit_and_duplicate_pr_rejected(self):
        plan=select(snapshot(),CTX)
        for change in ("labels","body","pr"):
            current=snapshot()
            if change=="labels":current["issues"][0]["labels"]=["agent-safe"]
            elif change=="body":current["issues"][0]["body"]+=" extra work"
            else:current["pull_requests"]=[{"state":"open","title":"Agent proposal: issue #50"}]
            with self.subTest(change=change),self.assertRaises(ValueError):recheck(current,plan,CTX)

    def test_weak_key_denied_before_reservation(self):
        db=MagicMock()
        with self.assertRaises(ValueError):reserve(db,select(snapshot(),CTX),b"",ctx=CTX,cost_digest="a"*64,now=NOW)
        db.execute.assert_not_called()

    def test_fake_authorization_cannot_replace_consumption(self):
        db=MagicMock()
        with self.assertRaises(ValueError):authorize(db,select(snapshot(),CTX),{"allowed":True},b"a"*32,ctx=CTX,now=NOW)
        db.execute.assert_not_called()

    def test_modified_task_with_stale_digest_denied(self):
        plan=select(snapshot(),CTX);plan["task"]["body"]+=" injected work"
        with self.assertRaises(ValueError):admit(receipt(plan),plan,ctx=CTX,now=NOW)


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'docs').mkdir();(self.root/'docs/sprint-2b-counting.md').write_text('original')

    def tearDown(self):self.tmp.cleanup()

    def test_valid_existing_doc_only(self):
        self.assertEqual(len(validate({"files":[{"path":"docs/sprint-2b-counting.md","content":"clarified"}]},self.root)),1)

    def test_paths_new_files_symlinks_and_oversized_rejected(self):
        link=self.root/'docs/sprint-2-link.md';link.symlink_to(self.root/'docs/sprint-2b-counting.md')
        paths=['../docs/sprint-2b-counting.md','/tmp/x','.github/workflows/x.yml','scripts/x.py',
               'docs/sprint-2-new.md','docs/sprint-2-link.md','docs/../docs/sprint-2b-counting.md']
        for path in paths:
            with self.subTest(path=path),self.assertRaises(ValueError):validate({"files":[{"path":path,"content":"x"}]},self.root)
        with self.assertRaises(ValueError):validate({"files":[{"path":"docs/sprint-2b-counting.md","content":"x"*32769}]},self.root)

    def test_model_commands_and_noops_rejected(self):
        for value in ({"files":[],"command":"publish"},{"files":[]},
                      {"files":[{"path":"docs/sprint-2b-counting.md","content":"original"}]}):
            with self.subTest(value=value),self.assertRaises(ValueError):validate(value,self.root)

    def test_publisher_uses_create_only_and_draft(self):
        calls=[]
        def api(method,path,body):
            calls.append((method,path,body));return {"sha":"b"*40,"number":1,"draft":True}
        publish(api,[{"path":"docs/sprint-2b-counting.md","content":"new"}],ctx=CTX,base_tree="c"*40)
        self.assertEqual([p for _,p,_ in calls],["git/trees","git/commits","git/refs","pulls"])
        self.assertTrue(all(m=="POST" for m,_,_ in calls))
        self.assertTrue(calls[-1][2]["draft"])
        self.assertNotIn("force",calls[2][2])


if __name__=="__main__":unittest.main()
