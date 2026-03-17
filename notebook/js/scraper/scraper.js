import { promises as fs } from 'fs';
import path from 'path';
import fastGlob from 'fast-glob';
import { csfd } from 'node-csfd-api';
import readline from 'readline';

const video_ext = [
    '.mp4', '.mkv', '.avi', 
    '.mov', '.wmv', '.flv'
];

/* node scraper.js [directory] [output_file]*/
const directory = path.resolve(process.argv[2]);
const output_file = process.argv[3];

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

function ask_question(query) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    return new Promise(resolve =>
        rl.question(query, ans => {
            rl.close();
            resolve(ans);
        }
    ));
}

async function process_files() {
    const files = await fastGlob(
        `${directory}/**/*`,
        { onlyFiles: true }
    );

    await fs.writeFile(output_file, '');

    for(const filePath of files) {
        const ext = path.extname(filePath).toLowerCase();
        if (!video_ext.includes(ext)) continue;

        const filename = path.basename(filePath);
        const searchName = normalize_name(filename);
        if (!searchName) continue;

        console.log(`searching: ${searchName}`);

        try {
            const results = await csfd.search(searchName);
            const movies = results.movies ?? [];

            if (movies.length === 0) {
                console.log('no match found');
                continue;
            }

            const bestMatch = movies[0];
            const movieDetail = await csfd.movie(bestMatch.id);

            console.log(
                `found: ${movieDetail.title} ` +
                `(${movieDetail.year})`
            );

            console.log(`csfd id: ${movieDetail.id}`);

            const userInput = await ask_question(
                'press enter to confirm or type csfd id: '
            );

            let csfd_id = bestMatch.id;
            if (userInput.trim()) {
                csfd_id = userInput.trim();
            }

            const relativePath = path.relative(
                directory, filePath
            );

            const outputEntry = {
                file_path: relativePath,
                csfd_id: csfd_id,
                title: movieDetail.title,
                year: movieDetail.year,
                genres: movieDetail.genres
            };

            await fs.appendFile(
                output_file,
                JSON.stringify(outputEntry) + '\n'
            );

            console.log(
                `saved: ${filename} -> csfd id: ${csfd_id}`
            );

        } catch (err) {
            console.log(
                `error for ${filename}: ` + 
                err.message
            );
        }
    }

    console.log('done');
}

process_files();
