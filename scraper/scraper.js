import { promises as fs } from 'fs';
import path from 'path';
import fastGlob from 'fast-glob';
import { csfd } from 'node-csfd-api';
import readline from 'readline';

const video_ext = [
    '.mp4', '.mkv', '.avi', 
    '.mov', '.wmv', '.flv'
];

const directory = path.resolve(process.argv[2]);
const output_file = process.argv[3];

if (!process.argv[2] || !process.argv[3]) {
    console.log('usage: node scraper.js [directory] [output_file]');
    process.exit(1);
}

function normalize_name(filename) {
    let name = filename.replace(path.extname(filename), '');
    name = name.replace(/\[[^\]]+\]/g, '');
    name = name.replace(/\([^)]+\)/g, '');
    name = name.replace(new RegExp(
        '/1080p|720p|2160p|' +
        'BluRay|BRRip|WEBRip|HDRip|DVDRip|' + 
        'x264|x265|HEVC|AVC|CZ|EN/gi'
    ), '' );

    name = name.replace(/[_\.]/g, ' ');
    name = name.replace(/\s+/g, ' ').trim();
    return name;
}

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

function ask_question(query) {
    return new Promise(resolve =>
        rl.question(query, ans => resolve(ans))
    );
}

async function process_files() {
    const files = await fastGlob(
        `${directory}/**/*`,
        { onlyFiles: true }
    );

    await fs.writeFile(output_file, '');

    for (const filePath of files) {
        const ext = path.extname(filePath).toLowerCase();
        if (!video_ext.includes(ext)) continue;

        const filename = path.basename(filePath);
        const searchName = normalize_name(filename);
        if (!searchName) continue;

        console.log(`searching file: ${filename}`);
        console.log(`searching: ${searchName}`);

        try {
            const results = await csfd.search(searchName);
            const movies = results?.movies ?? [];

            let csfd_id;

            if (movies.length === 0) {
                console.log('no match found');
            } else {
                console.log('\ntop 3 matches:');

                const top3 = movies.slice(0, 3);

                for (let i = 0; i < top3.length; i++) {
                    const m = top3[i];
                    try {
                        const detail = await csfd.movie(m.id);
                        if (!detail) continue;
                        console.log(
                            `${i + 1}. ${detail.title} (${detail.year}) [id: ${detail.id}]`
                        );
                    } catch {
                        continue;
                    }
                }
            }

            const input = await ask_question(
                '\n[Enter] = skip | 1-3 = select | or paste csfd id: '
            );

            if (!input.trim()) {
                console.log('skipped');
                continue;
            }

            const top3 = movies.slice(0, 3);

            if (['1', '2', '3'].includes(input.trim())) {
                const selected = top3[Number(input.trim()) - 1];
                if (!selected) {
                    console.log('invalid selection, skipping');
                    continue;
                }
                csfd_id = selected.id;
            } else {
                csfd_id = input.trim();
            }

            if (!csfd_id) {
                console.log('invalid selection, skipping');
                continue;
            }

            let movieDetail;
            try {
                movieDetail = await csfd.movie(csfd_id);
            } catch {
                console.log('failed to fetch movie detail, skipping');
                continue;
            }
            if (!movieDetail) {
                console.log('no details found, skipping');
                continue;
            }

            const relativePath = path.relative(directory, filePath);

            const outputEntry = {
                file_path: relativePath,
                csfd_id,
                title: movieDetail.title,
                year: movieDetail.year,
                genres: movieDetail.genres
            };

            await fs.appendFile(
                output_file,
                JSON.stringify(outputEntry) + '\n'
            );

            console.log(`saved: ${filename} -> ${movieDetail.title}`);

        } catch (err) {
            console.log(`error for ${filename}: ${err.message}`);
        }
    }

    rl.close();
    console.log('done');
}

process_files();
