// Optional visual verification using the bundled sharp package; no browser or installation.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const sharp = require(process.argv[2]);
const out = path.join(__dirname, 'output');
const dest = path.join(out, 'verification');
const sha256 = data => crypto.createHash('sha256').update(data).digest('hex');

async function main() {
  fs.mkdirSync(dest, {recursive: true});
  const records = [];
  for (let i = 1; i <= 5; i++) {
    const file = `uplift_interval${String(i).padStart(2, '0')}.svg`;
    const input = fs.readFileSync(path.join(out, file));
    const output = path.join(dest, file.replace('.svg', '_from_svg.png'));
    await sharp(input, {density: 110}).png().toFile(output);
    const metadata = await sharp(output).metadata();
    records.push({file, sha256: sha256(input), preview: path.relative(out, output),
      width: metadata.width, height: metadata.height});
  }
  fs.writeFileSync(path.join(dest, 'svg_render.json'), JSON.stringify({
    renderer: 'sharp/librsvg', versions: sharp.versions, files: records
  }, null, 2) + '\n');
  process.stdout.write('Rendered five actual SVG exports for visual inspection.\n');
}
main().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; });
