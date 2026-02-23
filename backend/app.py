from flask import Flask, request, jsonify
from flask_cors import CORS
from corrector import correct

app = Flask(__name__)
CORS(app, origins=["moz-extension://*"])


@app.post("/correct")
def correct_text():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text field required"}), 400
    if len(text) > 10_000:
        return jsonify({"error": "text too long (max 10000 chars)"}), 400
    return jsonify(correct(text))


@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5858, debug=False)
