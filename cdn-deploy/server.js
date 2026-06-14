const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const ROOT = __dirname;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml',
};

// Clean URL mapping — /stock → /stock.html
const cleanUrls = {
  '/': '/index.html',
  '/stock': '/stock.html',
  '/media': '/media.html',
  '/services': '/services.html',
};

http.createServer((req, res) => {
  let url = req.url.split('?')[0];

  // Clean URL support
  if (cleanUrls[url]) url = cleanUrls[url];

  // Try exact path, then .html suffix
  let filePath = path.join(ROOT, url);

  // Security: prevent directory traversal
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      // Try adding .html
      if (!url.endsWith('.html') && !path.extname(url)) {
        let htmlPath = path.join(ROOT, url + '.html');
        if (htmlPath.startsWith(ROOT)) {
          fs.readFile(htmlPath, (err2, data2) => {
            if (!err2) {
              res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
              res.end(data2);
              return;
            }
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end('404 Not Found: ' + url);
          });
          return;
        }
      }
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('404 Not Found: ' + url);
      return;
    }
    let ext = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'text/plain; charset=utf-8' });
    res.end(data);
  });
}).listen(PORT, '0.0.0.0', () => {
  console.log('============================================');
  console.log('  kunhuang.top Preview Server');
  console.log('  http://localhost:' + PORT);
  console.log('============================================');
});
