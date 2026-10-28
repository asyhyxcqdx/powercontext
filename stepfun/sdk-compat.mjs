// seekdb 1.4.0 validates SQL keywords even inside string literals returned by
// DBMS_HYBRID_SEARCH. Thus normal searches such as "update two balances" fail.
// Keep its SELECT/keyword/single-statement checks, but analyse SQL tokens instead
// of the contents of quoted data. This is scoped to the pinned SDK version.
export function maskQuotedSql(sql, backslashEscapes = true) {
  if (typeof sql !== 'string' || !sql.trim()) throw new Error('SQL must be nonempty');
  let result = '';
  for (let i = 0; i < sql.length;) {
    const quote = sql[i];
    if (quote === "'" || quote === '"' || quote === '`') {
      i++; let closed = false;
      while (i < sql.length) {
        if (backslashEscapes && sql[i] === '\\' && quote !== '`') { i += 2; continue; }
        if (sql[i] === quote) {
          if (sql[i + 1] === quote) { i += 2; continue; }
          i++; closed = true; break;
        }
        i++;
      }
      if (!closed) throw new Error('Unterminated SQL quote');
      result += ' quoted_value ';
    } else if (sql.startsWith('/*', i)) {
      if (sql.startsWith('/*!', i) || sql.startsWith('/*M!', i)) throw new Error('Executable SQL comments are not allowed');
      const end = sql.indexOf('*/', i + 2);
      if (end < 0) throw new Error('Unterminated SQL comment');
      result += ' '; i = end + 2;
    } else if (sql[i] === '#' || (sql.startsWith('--', i) && /\s/.test(sql[i + 2] || '\n'))) {
      const end = sql.indexOf('\n', i); i = end < 0 ? sql.length : end;
      result += ' ';
    } else { result += sql[i++]; }
  }
  return result;
}
export function fixHybridLiteralValidation(collection, backslashEscapes) {
  const validate = collection.validateDynamicSql;
  if (typeof validate !== 'function') throw new Error('Unsupported seekdb SDK version: hybrid SQL validator changed');
  collection.validateDynamicSql = sql => validate.call(collection, maskQuotedSql(sql, backslashEscapes));
  return collection;
}
