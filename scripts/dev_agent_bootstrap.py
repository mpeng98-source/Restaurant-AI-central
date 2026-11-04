"""One irreversible repository-wide claim, then one fixed billing probe.

This is not a coding agent or cost evidence producer. Model output is discarded.
"""
import hashlib
import json
import os
import re
import sys
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "mpeng98-source/Restaurant-AI-central"
WORKFLOW = ".github/workflows/dev-agent-bootstrap.yml"
ENVIRONMENT = "dev-agent-bootstrap-v1"
PROJECT = "proj_Nkd1G85QX72VHwdQ8mEg8CRa"
REF = "refs/tags/chubby-dev-agent-bootstrap-v1"
MODEL = "gpt-6-luna"
CONFIRMATION = "ONE PROBE; USD 0.01 ESTIMATE; NO RETRY"
# Standard text rates reviewed 2026-11-03: $0.10/M input, $0.50/M output.
# A generous 1,024 input-token allowance + 16 output tokens is < $0.01.
# This is an estimate, not a provider-enforced dollar cap.
REVIEW_VALID_UNTIL = 1794009600  # 2026-11-07 00:00 UTC; re-review before extension
PAYLOAD = {"model": MODEL, "input": "Reply OK.", "max_output_tokens": 16,
           "tools": [], "store": False, "service_tier": "default", "reasoning": {"effort": "none"}}


class Denied(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Denied()


class Transport:
    """Fixed hosts, no SDK retries, redirects, proxy credentials or raw logging."""
    def __init__(self):
        self.opener = build_opener(NoRedirect)

    def request(self, url, token, *, method="GET", body=None, project=None):
        allowed = (url.startswith("https://api.github.com/repos/" + REPOSITORY + "/")
                   if project is None else url == "https://api.openai.com/v1/responses")
        if not allowed or not token:
            raise Denied()
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json",
                   "Content-Type": "application/json"}
        if project is not None:
            headers["OpenAI-Project"] = project
        req = Request(url, data=None if body is None else json.dumps(body).encode(),
                      headers=headers, method=method)
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise Denied()
            return json.loads(raw)


def context(env, now):
    if (env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") != "refs/heads/main"
            or env.get("GITHUB_WORKFLOW_REF") != REPOSITORY + "/" + WORKFLOW + "@refs/heads/main"
            or env.get("GITHUB_RUN_ATTEMPT") != "1"
            or env.get("BOOTSTRAP_ENABLED") != "true"
            or env.get("CODING_ENABLED") != "false"
            or env.get("PROJECT_ID") != PROJECT
            or env.get("CONFIRMATION") != CONFIRMATION
            or type(now) is not int or not 0 < now < REVIEW_VALID_UNTIL):
        raise Denied()
    sha = env.get("GITHUB_SHA", "")
    run = env.get("GITHUB_RUN_ID", "")
    if (not re.fullmatch(r"[a-f0-9]{40}", sha) or env.get("APPROVED_SHA") != sha
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run)
            or not env.get("GH_TOKEN") or not env.get("OPENAI_API_KEY")):
        raise Denied()
    return {"repository": REPOSITORY, "project_id": PROJECT, "sha": sha,
            "run_id": run, "attempt": 1, "claimed_at": now,
            "estimated_allowance_usd": "0.01", "model": MODEL,
            "request_sha256": hashlib.sha256(json.dumps(PAYLOAD, sort_keys=True).encode()).hexdigest()}


def check_environment(api):
    settings = api("environments/" + ENVIRONMENT)
    rules = settings.get("protection_rules", [])
    reviewers = [r for r in rules if r.get("type") == "required_reviewers"]
    if (settings.get("can_admins_bypass") is not False or len(reviewers) != 1
            or reviewers[0].get("prevent_self_review") is not True
            or not reviewers[0].get("reviewers")
            or settings.get("deployment_branch_policy") != {
                "protected_branches": False, "custom_branch_policies": True}):
        raise Denied()
    policy = api("environments/" + ENVIRONMENT + "/deployment-branch-policies")
    branches = policy.get("branch_policies", [])
    if (policy.get("total_count") != 1 or len(branches) != 1
            or branches[0].get("name") != "main" or branches[0].get("type") != "branch"):
        raise Denied()


def check_tag_protection(api):
    # Runtime admission requires the permanent ledger to resist updates/deletes.
    # This does not protect against a trusted administrator disabling the rule.
    summaries = api("rulesets?includes_parents=true&per_page=100")
    if not isinstance(summaries, list): raise Denied()
    for summary in summaries:
        rid = summary.get("id")
        if type(rid) is not int or rid < 1: raise Denied()
        rule = api("rulesets/" + str(rid))
        refs = rule.get("conditions", {}).get("ref_name", {})
        if (rule.get("target") == "tag" and rule.get("enforcement") == "active"
                and rule.get("bypass_actors") == []
                and refs.get("exclude") == []
                and REF in refs.get("include", [])
                and {r.get("type") for r in rule.get("rules", [])} >= {"update", "deletion"}):
            return
    raise Denied()


def bootstrap(transport, env, now):
    binding = context(env, now)

    def api(path, method="GET", body=None):
        return transport.request("https://api.github.com/repos/" + REPOSITORY + "/" + path,
                                 env["GH_TOKEN"], method=method, body=body)

    check_environment(api)
    check_tag_protection(api)
    if api("git/ref/heads/main").get("object", {}).get("sha") != binding["sha"]:
        raise Denied()
    # Annotated tag stores provenance, but only atomic create-ref spends the
    # repository-wide opportunity. Never update/delete it, including on failure.
    tag = api("git/tags", "POST", {"tag": REF.removeprefix("refs/tags/"),
              "message": json.dumps(binding, sort_keys=True),
              "object": binding["sha"], "type": "commit"})
    tag_sha = tag.get("sha", "")
    if not isinstance(tag_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", tag_sha):
        raise Denied()
    claimed = api("git/refs", "POST", {"ref": REF, "sha": tag_sha})
    if (claimed.get("ref") != REF or claimed.get("object", {}).get("sha") != tag_sha
            or claimed.get("object", {}).get("type") != "tag"):
        raise Denied()
    # The claim is committed before the sole paid call. HTTP failure, timeout,
    # response rejection, crash or cancellation permanently burns this claim.
    response = transport.request("https://api.openai.com/v1/responses", env["OPENAI_API_KEY"],
                                 method="POST", body=PAYLOAD, project=PROJECT)
    usage = response.get("usage", {})
    if (response.get("model") != MODEL or response.get("status") != "completed"
            or type(usage.get("input_tokens")) is not int
            or type(usage.get("output_tokens")) is not int
            or not 0 < usage["input_tokens"] <= 1024
            or not 0 < usage["output_tokens"] <= 16):
        raise Denied()
    # This is local usage, never signed Costs API evidence or a coding permit.
    return {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"]}


def main():
    try:
        usage = bootstrap(Transport(), os.environ, int(time.time()))
    except Exception:
        print("Bootstrap denied or incomplete; inspect permanent claim; never retry automatically", file=sys.stderr)
        return 2
    print("One probe completed; claim retained; input_tokens=" + str(usage["input_tokens"])
          + "; output_tokens=" + str(usage["output_tokens"])
          + "; await actual current-day Costs API evidence; coding remains disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
