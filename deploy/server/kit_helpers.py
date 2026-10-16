"""Standard-library validation helpers; invoked only by the deployment scripts."""
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
from urllib.parse import urlsplit


def fail(message):
    raise SystemExit(message)


def archive(path):
    with tarfile.open(path, "r:*") as tar:
        seen = set()
        for member in tar:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or "\\" in member.name
                    or any(ord(c) < 32 for c in member.name)
                    or not (member.isfile() or member.isdir())):
                fail("Archive must contain only relative regular files/directories: " + member.name)
            if str(name) in seen:
                fail("Duplicate archive member: " + member.name)
            seen.add(str(name))


def ports(mode, numbers):
    rows = subprocess.check_output(["ss", "-H", "-ltnp"], text=True).splitlines()
    for number in numbers:
        listeners = [r.split()[3] for r in rows if r.split()[3].rsplit(":", 1)[-1] == number]
        if mode == "free":
            if listeners:
                fail("BLOCKER: port " + number + " already listens on " + ", ".join(listeners))
        elif mode == "loopback":
            if not listeners or any(a != "127.0.0.1:" + number for a in listeners):
                fail("Port " + number + " must listen only on 127.0.0.1; got " + repr(listeners))
        else:
            fail("Unknown port check")
        print("Port", number, mode, "OK")


def ollama_env():
    raw = sys.stdin.read().strip()
    if not raw.startswith("Environment="):
        fail("No effective Ollama environment")
    actual = dict(item.split("=", 1) for item in shlex.split(raw.partition("=")[2]))
    expected = {
        "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_NO_CLOUD": "1",
        "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_KEEP_ALIVE": "30m", "OLLAMA_CONTEXT_LENGTH": "8192",
    }
    for key, value in expected.items():
        if actual.get(key) != value:
            fail("Unexpected effective environment for " + key)
        print(key + "=" + value)


def model_digest(path, expected):
    manifest = json.loads(Path(path).read_text())
    layers = [layer["digest"] for layer in manifest.get("layers", [])
              if layer.get("mediaType") == "application/vnd.ollama.image.model"]
    if layers != [expected]:
        fail("Model layer digest mismatch: " + repr(layers))
    print("Verified model layer:", expected)


def nginx_candidate(source, output):
    text = Path(source).read_text()
    anchor = re.compile(r"^\s*include\s+/etc/nginx/snippets/mazkira\.conf;[^\n]*$", re.M)
    matches = list(anchor.finditer(text))
    if len(matches) != 1:
        fail("Expected exactly one mazkira include anchor in default")
    # Locate server blocks using tokens, ignoring comments and quoted braces.
    token = re.compile(r'#.*?$|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[{};]|[^\s{};#]+', re.M)
    stack, statement, servers = [], [], []
    for match in token.finditer(text):
        value = match.group()
        if value.startswith("#"):
            continue
        if value == "{":
            stack.append((statement == ["server"], match.end()))
            statement = []
        elif value == "}":
            if not stack:
                fail("Unbalanced nginx braces")
            server, start = stack.pop()
            if server:
                servers.append((start, match.start()))
            statement = []
        elif value == ";":
            statement = []
        else:
            statement.append(value)
    if stack:
        fail("Unbalanced nginx braces")
    enclosing = [(a, b) for a, b in servers if a <= matches[0].start() < b]
    if len(enclosing) != 1:
        fail("Anchor is not in exactly one server block")
    a, b = enclosing[0]
    body = re.sub(r"#.*", "", text[a:b])
    names = re.findall(r"\bserver_name\s+([^;]+);", body)
    listens = re.findall(r"\blisten\s+([^;]+);", body)
    if not any("dikenocracy.com" in line.split() for line in names):
        fail("Anchor server_name does not contain dikenocracy.com")
    if not any(re.search(r"(?:^|:)443(?:\s|$)", line) and "ssl" in line.split() for line in listens):
        fail("Anchor server block is not HTTPS on 443")
    includes = list(re.finditer(r"^[ \t]*include\s+/etc/nginx/snippets/dkp-lab-keeper\.conf;[^\n]*\n?", text, re.M))
    if len(includes) > 1:
        fail("Duplicate DKP includes; inspect manually")
    if includes:
        old = includes[0]
        if not (a <= old.start() < b):
            fail("DKP include already exists in another server block")
        text = text[:old.start()] + text[old.end():]
    match = anchor.search(text)
    from datetime import datetime, timezone
    date = datetime.now(timezone.utc).date().isoformat()
    line = "    include /etc/nginx/snippets/dkp-lab-keeper.conf;  # DKP lab + Keeper (added " + date + ")"
    text = text[:match.end()] + "\n" + line + text[match.end():]
    Path(output).write_text(text)


def routes(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("routes")
    if not isinstance(data, list) or not data:
        fail("ROUTES.json must be a nonempty list, or an object with a routes list")
    paths = []
    for item in data:
        if isinstance(item, dict):
            values = [item[key] for key in ("path", "route", "url") if key in item]
            if len(values) != 1:
                fail("Route objects must have exactly one path, route, or url field")
            item = values[0]
        if not isinstance(item, str):
            fail("Route must be a string or route object")
        parsed = urlsplit(item)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme != "https" or parsed.netloc != "dikenocracy.com":
                fail("Absolute routes must use https://dikenocracy.com")
        elif not item.startswith("/") or item.startswith("//"):
            fail("Routes must start with / or https://dikenocracy.com")
        if (parsed.query or parsed.fragment or ".." in PurePosixPath(parsed.path).parts
                or any(c.isspace() or ord(c) < 32 for c in item) or "\\" in item):
            fail("Unsafe or unsupported route")
        if parsed.path not in paths:
            paths.append(parsed.path)
    print("\n".join(paths))


def loader(path):
    from html.parser import HTMLParser

    class Scripts(HTMLParser):
        count = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "script" and attrs.get("src") == "/keeper/keeper-loader.js" and "defer" in attrs:
                self.count += 1

    parser = Scripts()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    if parser.count != 1:
        fail("Expected exactly one deferred Keeper loader tag")


def public_ip(value):
    # Require an operator-supplied address; never infer it from a third-party service.
    addr = ipaddress.ip_address(value)
    if not addr.is_global:
        fail("PUBLIC_IP must be a global public IP literal")
    print("[" + str(addr) + "]" if addr.version == 6 else addr)


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action == "archive":
        archive(*args)
    elif action == "ports":
        ports(args[0], args[1:])
    elif action == "ollama-env":
        ollama_env()
    elif action == "model-digest":
        model_digest(*args)
    elif action == "nginx-candidate":
        nginx_candidate(*args)
    elif action == "routes":
        routes(*args)
    elif action == "loader":
        loader(*args)
    elif action == "public-ip":
        public_ip(*args)
    else:
        fail("Unknown helper action")
