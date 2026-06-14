const initSqlJs = require('sql.js');
const fs = require('fs');

async function upgrade() {
  const SQL = await initSqlJs();
  const buf = fs.readFileSync('C:/Users/五颜六色/stock-analysis-app-main/app.db');
  const db = new SQL.Database(buf);

  // Check user
  let stmt = db.prepare("SELECT id, username, membership FROM users WHERE username='18622089038'");
  if (!stmt.step()) {
    console.log('用户不存在，请先注册');
    db.close();
    return;
  }
  let row = stmt.getAsObject();
  console.log('当前:', row.username, row.membership);
  stmt.free();

  // Upgrade
  db.run("UPDATE users SET membership='svip', membership_expires='2036-06-14' WHERE username='18622089038'");

  // Verify
  stmt = db.prepare("SELECT id, username, membership, membership_expires FROM users WHERE username='18622089038'");
  stmt.step();
  row = stmt.getAsObject();
  console.log('升级后:', JSON.stringify(row));
  stmt.free();

  // Save to disk
  const data = db.export();
  fs.writeFileSync('C:/Users/五颜六色/stock-analysis-app-main/app.db', Buffer.from(data));
  console.log('✅ 已保存');
  db.close();
}
upgrade();
