"""GET-only security evidence diagnostic; never authorizes a paid operation."""
import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REPOSITORY = 'mpeng98-source/Restaurant-AI-central'
WORKFLOW = '.github/workflows/dev-agent-bootstrap-runtime-diagnostic.yml'
ENVIRONMENT = 'dev-agent-bootstrap-v1'
RULESET_ID = 26511987
REF = 'refs/tags/chubby-dev-agent-bootstrap-v1'
BASE = 'https://api.github.com/repos/' + REPOSITORY + '/'
PATHS = {
    'main': 'git/ref/heads/main',
    'environment': 'environments/' + ENVIRONMENT,
    'branch_policy': 'environments/' + ENVIRONMENT + '/deployment-branch-policies',
    'ruleset': 'rulesets/' + str(RULESET_ID),
}


class Unknown(Exception):
    pass


class Failed(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise Unknown()


class Transport:
    def __init__(self):
        # Never use proxy credentials, follow redirects, or retry a request.
        self.opener = build_opener(ProxyHandler({}), NoRedirect)

    def get(self, path, token):
        if path not in PATHS.values() or not token:
            raise Failed()
        request = Request(BASE + path, method='GET', headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
        with self.opener.open(request, timeout=15) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise Unknown()
            return json.loads(raw)


def context(env):
    sha = env.get('GITHUB_SHA', '')
    if (env.get('GITHUB_REPOSITORY') != REPOSITORY
            or env.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or env.get('GITHUB_REF') != 'refs/heads/main'
            or env.get('GITHUB_WORKFLOW_REF') != REPOSITORY + '/' + WORKFLOW + '@refs/heads/main'
            or env.get('GITHUB_RUN_ATTEMPT') != '1'
            or not re.fullmatch('[a-f0-9]{40}', sha)
            or env.get('APPROVED_SHA') != sha or env.get('WORKFLOW_SHA') != sha
            or not re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', ''))
            or not env.get('GITHUB_ACTOR') or not env.get('GH_TOKEN')):
        raise Failed()


def obj(value):
    if type(value) is not dict:
        raise Unknown()
    return value


def field(value, name, kind):
    result = obj(value).get(name)
    if type(result) is not kind:
        raise Unknown()
    return result


def main_ref(value, env):
    if field(field(value, 'object', dict), 'sha', str) != env['GITHUB_SHA']:
        raise Failed()


def environment(value, env):
    if field(value, 'name', str) != ENVIRONMENT:
        raise Failed()
    if field(value, 'can_admins_bypass', bool):
        raise Failed()
    rules = field(value, 'protection_rules', list)
    reviewers = [r for r in rules if field(r, 'type', str) == 'required_reviewers']
    if len(reviewers) != 1:
        raise Failed()
    rule = reviewers[0]
    if not field(rule, 'prevent_self_review', bool):
        raise Failed()
    accounts = field(rule, 'reviewers', list)
    # Require an independently named user; no assumptions about team membership.
    independent = False
    for account in accounts:
        kind = field(account, 'type', str)
        identity = field(account, 'reviewer', dict)
        if kind not in ('User', 'Team'):
            raise Unknown()
        if kind == 'User':
            login = field(identity, 'login', str)
            if not re.fullmatch('[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', login):
                raise Unknown()
            if login.lower() != env['GITHUB_ACTOR'].lower():
                independent = True
    if not independent:
        raise Failed()
    policy = field(value, 'deployment_branch_policy', dict)
    if (field(policy, 'protected_branches', bool)
            or not field(policy, 'custom_branch_policies', bool)):
        raise Failed()


def branch_policy(value, env):
    count = field(value, 'total_count', int)
    policies = field(value, 'branch_policies', list)
    if count != 1 or len(policies) != 1:
        raise Failed()
    if field(policies[0], 'name', str) != 'main' or field(policies[0], 'type', str) != 'branch':
        raise Failed()


def ruleset(value, env):
    if (field(value, 'id', int) != RULESET_ID or field(value, 'target', str) != 'tag'
            or field(value, 'source_type', str) != 'Repository'
            or field(value, 'source', str) != REPOSITORY
            or field(value, 'enforcement', str) != 'active'):
        raise Failed()
    # Missing/redacted metadata is UNKNOWN, never an inferred empty bypass list.
    if field(value, 'bypass_actors', list) != []:
        raise Failed()
    refs = field(field(value, 'conditions', dict), 'ref_name', dict)
    if field(refs, 'include', list) != [REF] or field(refs, 'exclude', list) != []:
        raise Failed()
    types = {field(rule, 'type', str) for rule in field(value, 'rules', list)}
    if not {'update', 'deletion'} <= types:
        raise Failed()


def check(operation):
    try:
        operation()
        return 'PASS'
    except Failed:
        return 'FAIL'
    except HTTPError as error:
        return 'FAIL' if error.code == 404 else 'UNKNOWN'
    except Exception:
        # Never log exception text, URL, headers, tokens or response content.
        return 'UNKNOWN'


def diagnose(transport, env):
    results = {'context': check(lambda: context(env))}
    if results['context'] != 'PASS':
        return results
    for stage, validator in (('main', main_ref), ('environment', environment),
                             ('branch_policy', branch_policy), ('ruleset', ruleset)):
        results[stage] = check(lambda: validator(transport.get(PATHS[stage], env['GH_TOKEN']), env))
    # Detect main movement while reading the snapshot. This is not an atomic attestation.
    results['main_after'] = check(lambda: main_ref(transport.get(PATHS['main'], env['GH_TOKEN']), env))
    return results


def main():
    try:
        results = diagnose(Transport(), os.environ)
    except Exception:
        results = {'diagnostic': 'UNKNOWN'}
    for stage, status in results.items():
        print(stage + ': ' + status)
    passed = all(status == 'PASS' for status in results.values())
    print('overall: ' + ('PASS' if passed else 'DENIED'))
    print('Diagnostic only; no claim or paid execution authorized')
    return 0 if passed else 2


if __name__ == '__main__':
    sys.exit(main())
