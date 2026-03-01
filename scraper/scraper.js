import { promises as fs } from 'fs';
import path from 'path';
import fastGlob from 'fast-glob';
import { csfd } from 'node-csfd-api';
import readline from 'readline';

const VIDEO_EXT = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv'];
const FOLDER = path.resolve(process.argv[2]);       // make absolute internally
const OUTPUT_FILE = process.argv[3];

function normalizeName(filename) {
  let name = filename.replace(path.extname(filename), '');
  name = name.replace(/\[[^\]]+\]/g, '');
  name = name.replace(/\([^)]+\)/g, '');
  name = name.replace(
    /1080p|720p|2160p|BluRay|BRRip|WEBRip|HDRip|DVDRip|x264|x265|HEVC|AVC|CZ|EN/gi,
    ''
  );
  name = name.replace(/[_\.]/g, ' ');
  name = name.replace(/\s+/g, ' ').trim();
  return name;
}

function askQuestion(query) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
  return new Promise(resolve =>
    rl.question(query, ans => {
      rl.close();
      resolve(ans);
    })
  );
}

async function processFiles() {
  const files = await fastGlob(`${FOLDER}/**/*`, { onlyFiles: true });
  await fs.writeFile(OUTPUT_FILE, '');

  for (const filePath of files) {
    const ext = path.extname(filePath).toLowerCase();
    if (!VIDEO_EXT.includes(ext)) continue;

    const filename = path.basename(filePath);
    const searchName = normalizeName(filename);
    if (!searchName) continue;

    console.log(`\nsearching: ${searchName}`);

    try {
      const results = await csfd.search(searchName);
      const movies = results.movies ?? [];

      if (movies.length === 0) {
        console.log('no match found');
        continue;
      }

      const bestMatch = movies[0];
      const movieDetail = await csfd.movie(bestMatch.id);

      console.log(`found: ${movieDetail.title} (${movieDetail.year})`);
      console.log(`csfd id: ${movieDetail.id}`);

      const userInput = await askQuestion(
        'press enter to confirm or type csfd id: '
      );

      let csfd_id = bestMatch.id;
      if (userInput.trim()) {
        csfd_id = userInput.trim();
      }

      const relativePath = path.relative(FOLDER, filePath);

      const outputEntry = {
        file_path: relativePath,
        csfd_id: csfd_id,
        title: movieDetail.title,
        year: movieDetail.year,
        genres: movieDetail.genres
      };

      await fs.appendFile(
        OUTPUT_FILE,
        JSON.stringify(outputEntry) + '\n'
      );

      console.log(`saved: ${filename} -> csfd id: ${csfd_id}`);

    } catch (err) {
      console.error(`error for ${filename}:`, err.message);
    }
  }

  console.log('\ndone!');
}

processFiles();
