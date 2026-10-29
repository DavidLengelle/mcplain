import axios from "axios";

export function makeClient() {
  return axios.create({ timeout: 10000 });
}
