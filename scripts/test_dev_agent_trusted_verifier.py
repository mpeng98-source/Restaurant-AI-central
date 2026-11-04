import unittest
from unittest.mock import MagicMock
from dev_agent_signed_evidence import sign
from dev_agent_trusted_verifier import verify_and_consume

KEY=b"k"*32
NOW=1700000000
SHA="a"*40
BASE={"kind":"codex_permit","run_id":123,"issue_number":39,"head_sha":SHA,
      "project_id":"proj_agent","issued_at":NOW,"expires_at":NOW+120,
      "nonce":"b"*32}


def fake_db(result=True):
    db=MagicMock()
    cursor=MagicMock()
    cursor.fetchone.return_value=(result,)
    db.cursor.return_value.__enter__.return_value=cursor
    return db,cursor


def check(db,envelope,**overrides):
    params=dict(now=NOW+10,run_id=123,issue_number=39,head_sha=SHA,project_id="proj_agent")
    params.update(overrides)
    return verify_and_consume(db,envelope,KEY,**params)


class TrustedVerifierTests(unittest.TestCase):
    def test_valid_consumed_once(self):
        db,cur=fake_db(True)
        self.assertTrue(check(db,sign(BASE,KEY)))
        cur.execute.assert_called_once()

    def test_replay_denied_by_database(self):
        db,cur=fake_db(False)
        self.assertFalse(check(db,sign(BASE,KEY)))

    def test_tampered_signature_never_reaches_database(self):
        db,cur=fake_db()
        e=sign(BASE,KEY)
        e["payload"]["issue_number"]=40
        with self.assertRaises(ValueError):
            check(db,e)
        cur.execute.assert_not_called()

    def test_expired_never_reaches_database(self):
        db,cur=fake_db()
        with self.assertRaises(ValueError):
            check(db,sign(BASE,KEY),now=NOW+121)
        cur.execute.assert_not_called()

    def test_wrong_run_never_reaches_database(self):
        db,cur=fake_db()
        with self.assertRaises(ValueError):
            check(db,sign(BASE,KEY),run_id=999)
        cur.execute.assert_not_called()

    def test_wrong_sha_never_reaches_database(self):
        db,cur=fake_db()
        with self.assertRaises(ValueError):
            check(db,sign(BASE,KEY),head_sha="c"*40)
        cur.execute.assert_not_called()

    def test_missing_database_fails_closed(self):
        db,cur=fake_db()
        cur.execute.side_effect=RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            check(db,sign(BASE,KEY))


if __name__=="__main__":
    unittest.main()
