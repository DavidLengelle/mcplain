import https from "https";
const mirror = process.env.NOTES_MIRROR || "https://downloads.example.invalid";
https.get(`${mirror}/notes-cli-1.0.0.tar.gz`);
