const http = process.getBuiltinModule("node:http");

const FORWARDED_FOR = "x-forwarded-for";
const originalEmit = http.Server.prototype.emit;

function appendClientAddress(request) {
  const address = request.socket && request.socket.remoteAddress;
  if (!address) {
    return;
  }
  const previous = request.headers[FORWARDED_FOR];
  if (typeof previous === "string" && previous.trim() !== "") {
    request.headers[FORWARDED_FOR] = `${previous}, ${address}`;
  } else {
    request.headers[FORWARDED_FOR] = address;
  }
}

http.Server.prototype.emit = function emit(event, request, ...rest) {
  if (event === "request" && request) {
    appendClientAddress(request);
  }
  return originalEmit.call(this, event, request, ...rest);
};

module.exports = { appendClientAddress };
