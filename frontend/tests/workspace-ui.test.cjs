const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const ts = require('typescript');

function loadTypeScriptModule(relativePath) {
  const filename = path.join(__dirname, '..', relativePath);
  const source = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const loaded = { exports: {} };
  new Function('module', 'exports', 'require', output)(loaded, loaded.exports, require);
  return loaded.exports;
}

const review = loadTypeScriptModule('src/lib/applicantReview.ts');
const intake = loadTypeScriptModule('src/lib/intake.ts');

const items = [
  { application_id: 'a', candidate_name: 'A', rank_number: 2, matching_status: 'MEETS_MANDATORY', matching_score: 90, evidence_coverage: 0.9, needs_verification: false, has_mismatch: false, application_status: 'IN_REVIEW', file_processing_status: 'COMPLETED' },
  { application_id: 'b', candidate_name: 'B', rank_number: 1, matching_status: 'MEETS_MANDATORY', matching_score: 80, evidence_coverage: 0.5, needs_verification: true, has_mismatch: false, application_status: 'IN_REVIEW', file_processing_status: 'COMPLETED' },
  { application_id: 'c', candidate_name: 'C', rank_number: null, matching_status: 'NOT_ASSESSED', matching_score: null, evidence_coverage: null, needs_verification: false, has_mismatch: false, application_status: 'NEW', file_processing_status: 'NEEDS_HR_REVIEW', has_duplicate_warning: true },
];

test('applicant queues separate file review, duplicate and verification work', () => {
  const counts = review.applicantQueueCounts(items);
  assert.equal(counts.ALL, 3);
  assert.equal(counts.FILE_REVIEW, 1);
  assert.equal(counts.DUPLICATE, 1);
  assert.equal(counts.NEEDS_VERIFICATION, 1);
  assert.equal(counts.MEETS_MANDATORY, 1);
  assert.deepEqual(review.filterAndSortApplicantItems(items, 'NEEDS_VERIFICATION', '', 'REVIEW_PRIORITY').map(item => item.application_id), ['b']);
});

test('review priority puts file problems before ranking order', () => {
  assert.deepEqual(review.sortApplicantItems(items, 'REVIEW_PRIORITY').map(item => item.application_id), ['c', 'b', 'a']);
  assert.deepEqual(review.sortApplicantItems(items, 'COVERAGE_ASC').map(item => item.application_id), ['b', 'a', 'c']);
});

test('intake validation marks duplicates as warnings and invalid files as blockers', () => {
  const result = intake.validateIntakeFiles([
    { name: 'cv.pdf', size: 100 },
    { name: 'CV.PDF', size: 120 },
    { name: 'notes.txt', size: 100 },
    { name: 'large.pdf', size: 10_000_001 },
  ]);
  assert.equal(result.items[0].status, 'WARNING');
  assert.equal(result.items[1].status, 'WARNING');
  assert.equal(result.items[2].status, 'INVALID');
  assert.equal(result.items[3].status, 'INVALID');
  assert.match(result.batchError, /chưa hợp lệ/);
});


test('route priority can be moved without changing or duplicating the original list', () => {
  const { moveRoute } = loadTypeScriptModule('src/lib/orderedRoutes.ts');
  const routes = ['first', 'second', 'third'];
  assert.deepEqual(moveRoute(routes, 1, -1), ['second', 'first', 'third']);
  assert.deepEqual(moveRoute(routes, 1, 1), ['first', 'third', 'second']);
  assert.deepEqual(routes, ['first', 'second', 'third']);
  assert.deepEqual(moveRoute(routes, 0, -1), routes);
  assert.deepEqual(moveRoute(routes, 2, 1), routes);
  assert.deepEqual(moveRoute(routes, -1, 1), routes);
});
