import fs from "fs";
import { csfd } from "node-csfd-api";

const START_ID = 1;
const END_ID = 100_000;
const DELAY_MS = 500;

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function appendToJSON(movie) {
    const movieData = {
        id: movie.id,
        title: movie.title,
        year: movie.year || null,
        rating: movie.rating || null,
        ratingCount: movie.ratingCount || null,
        genres: movie.genres || [],
        directors: movie.creators?.directors?.map(d => d.name) || [],
        writers: movie.creators?.writers?.map(w => w.name) || [],
        actors: movie.creators?.actors?.map(a => a.name) || []
    };

    const line = JSON.stringify(movieData) + "\n";
    fs.appendFileSync("movies.jsonl", line, "utf8");
}

function initJSON() {
    fs.writeFileSync("movies.jsonl", "", "utf8");
}

async function main() {
    console.log("scraper started");
    initJSON();

    for (let id = START_ID; id <= END_ID; id++) {
        try {
            console.log(`id: ${id}`);

            const detail = await csfd.movie(id);

            // if (!detail || detail.type !== "film") {
            //   continue;
            // }

            // if (!detail.ratingCount || detail.ratingCount < 100) {
            //   continue;
            // }

            appendToJSON(detail);
            collected++;

            console.log(`saved: ${detail.title} (${id}/${END_ID})`);

            await sleep(DELAY_MS);
        } catch (error) {
            continue;
        }
    }

    console.log("scraping finished");
}

main();
