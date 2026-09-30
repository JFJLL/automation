const fs = require('fs');
const [,, file, jsonPath] = process.argv;
const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
let content = fs.readFileSync(file, 'utf8').replace(/
/g, '
');
const target = data.target.replace(/
/g, '
');
const replacement = data.replacement.replace(/
/g, '
');
if (!content.includes(target)) {
    console.error('TARGET NOT FOUND IN ' + file);
    process.exit(1);
}
content = content.replace(target, replacement);
fs.writeFileSync(file, content, 'utf8');
console.log('PATCHED ' + file);
