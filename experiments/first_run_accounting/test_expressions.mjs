// Install pinned official evaluator outside the checkout, without lifecycle scripts:
// npm install --prefix /tmp/canary-expressions --cache /tmp/canary-npm-cache --ignore-scripts --no-audit --no-fund @actions/expressions@0.3.25
// node experiments/first_run_accounting/test_expressions.mjs
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {registerHooks} from 'node:module';
const root=process.env.EXPRESSIONS_PACKAGE || '/tmp/canary-expressions/node_modules/@actions/expressions';
assert.equal(JSON.parse(readFileSync(root+'/package.json')).version,'0.3.25');
// The published ESM uses extensionless internal imports; resolve only those
// inside this exact package. No evaluator source or behavior is modified.
registerHooks({resolve(specifier,context,nextResolve) {
  try {return nextResolve(specifier,context);}
  catch(error) {
    if(['ERR_MODULE_NOT_FOUND','ERR_UNSUPPORTED_DIR_IMPORT'].includes(error.code) && specifier.startsWith('.') && context.parentURL?.startsWith(pathToFileURL(root+'/dist/').href))
      return nextResolve(specifier+(existsSync(new URL(specifier+'.js',context.parentURL))?'.js':'/index.js'),context);
    throw error;
  }
}});
const {Parser,Lexer,Evaluator,data}=await import(pathToFileURL(root+'/dist/index.js'));
const workflow=readFileSync(new URL('./workflow.candidate.yml',import.meta.url),'utf8');
const expression=workflow.match(/COST_DIGEST: \$\{\{ (.+) \}\}/)[1];
function value(v) {
  if(typeof v==='string')return new data.StringData(v);
  if(typeof v==='boolean')return new data.BooleanData(v);
  return new data.Dictionary(...Object.entries(v).map(([key,v])=>({key,value:value(v)})));
}
function evaluate(expr,context) {
  return new Evaluator(new Parser(new Lexer(expr).lex().tokens,Object.keys(context),[]).parse(),value(context)).evaluate().coerceString();
}
const context=receipt=>({needs:{ingest:{outputs:{receipt}}}});
assert.throws(()=>evaluate('fromJSON(needs.ingest.outputs.receipt).cost_digest',context('')));
assert.equal(evaluate(expression,context('')),'');
assert.equal(evaluate(expression,{needs:{ingest:{outputs:{}}}}),'');
assert.equal(evaluate(expression,context('{"cost_digest":"fixture-digest"}')),'fixture-digest');
assert.throws(()=>evaluate(expression,context('{malformed')));
const reserve=workflow.slice(workflow.indexOf('\n  reserve:'),workflow.indexOf('\n  authorize:'));
const condition=reserve.match(/if: \$\{\{ (!inputs\.unknown_cost_exception) \}\}/)[1];
assert.equal(evaluate(condition,{inputs:{unknown_cost_exception:true}}),'false');
assert.equal(evaluate(condition,{inputs:{unknown_cost_exception:false}}),'true');
console.log('7 expression assertions passed with @actions/expressions 0.3.25; no GitHub execution');
