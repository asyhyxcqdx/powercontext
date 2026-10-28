import test from 'node:test';
import assert from 'node:assert/strict';
import { splitText, collectionName, retrievalMetrics } from '../public/config.js';
test('Unicode chunks preserve source order with bounded overlap', () => {
  const text = '文😀字 abc '.repeat(220);
  const chunks = splitText(text, 90, 10);
  assert.ok(chunks.length > 10);
  let next = 0;
  for (const chunk of chunks) {
    assert.ok(Array.from(chunk).length <= 90);
    const index = text.indexOf(chunk, Math.max(0, next - 25));
    assert.ok(index >= 0);
    next = index + chunk.length;
    assert.ok(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(chunk));
  }
  assert.deepEqual(splitText('  '), []);
});
test('different precisions and libraries never share a collection', () => {
  assert.notEqual(collectionName('papers', 'q8'), collectionName('papers', 'fp32'));
  assert.notEqual(collectionName('papers', 'q8'), collectionName('notes', 'q8'));
  assert.throws(() => collectionName('../bad', 'q8'));
  assert.throws(() => collectionName('good', 'bogus'));
});
test('retrieval metrics include missed labels and reward earlier results', () => {
  assert.deepEqual(retrievalMetrics(['a','b'], ['a','b']), { recall: 1, ndcg: 1 });
  assert.equal(retrievalMetrics(['x','a'], ['a','b']).recall, 0.5);
  assert.ok(retrievalMetrics(['a','x'], ['a']).ndcg > retrievalMetrics(['x','a'], ['a']).ndcg);
  assert.equal(retrievalMetrics(['a','a'], ['a','b']).recall, 0.5);
});

import { maskQuotedSql, fixHybridLiteralValidation } from '../sdk-compat.mjs';
import { Collection } from 'seekdb';
function checkSql(sql, escapes = true) {
  const collection = Object.create(Collection.prototype);
  fixHybridLiteralValidation(collection, escapes);
  return collection.validateDynamicSql(sql);
}
test('ordinary SQL words in quoted search text do not fail the SDK guard', () => {
  assert.doesNotThrow(() => checkSql("SELECT * FROM t WHERE MATCH(document) AGAINST('how to update or delete records; restore backups')"));
  assert.doesNotThrow(() => checkSql("SELECT `update`, 'don''t delete', 'a\\\'b UPDATE' FROM t"));
  assert.doesNotThrow(() => checkSql("SELECT /*+ PARALLEL(1) */ 'hello --world' FROM t;"));
});
test('SQL validation still rejects real writes, multiple statements and executable comments', () => {
  for (const sql of ["UPDATE t SET value=1", "SELECT 1; DELETE FROM t", "SELECT 'ok' INTO OUTFILE '/tmp/out'", "SELECT 1 /*!50000 INTO OUTFILE '/tmp/out' */", "SELECT 'unterminated"])
    assert.throws(() => checkSql(sql));
  assert.throws(() => checkSql("SELECT 'a\\'; DELETE FROM t; --'", false));
  assert.equal(maskQuotedSql("SELECT 'UPDATE'"), 'SELECT  quoted_value ');
});
