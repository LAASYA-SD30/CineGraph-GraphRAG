import os
import re
import pandas as pd
from flask import Flask, request, render_template_string, jsonify
from neo4j import GraphDatabase
from google import genai

app = Flask(__name__)

# Securely load credentials from environment variables
NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Configure drivers
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
gemini = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.5-flash"

QUERIES = {
    "movie": """
        MATCH (m:Movie)
        WHERE toLower(m.title) CONTAINS toLower($term)
        RETURN m.title AS title,
               m.released AS year,
               m.tagline AS tagline
        LIMIT 10
    """,

    "cast": """
        MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
        WHERE toLower(m.title) CONTAINS toLower($term)
        RETURN m.title AS movie,
               m.released AS year,
               p.name AS actor,
               r.roles AS roles
        LIMIT 30
    """,

    "actor": """
        MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
        WHERE toLower(p.name) CONTAINS toLower($term)
        RETURN p.name AS actor,
               m.title AS movie,
               m.released AS year,
               r.roles AS roles
        LIMIT 30
    """,

    "role": """
        MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
        WHERE any(role IN coalesce(r.roles, [])
                  WHERE toLower(role) CONTAINS toLower($term))
        RETURN p.name AS actor,
               m.title AS movie,
               r.roles AS roles
        LIMIT 20
    """,

    "director": """
        MATCH (p:Person)-[:DIRECTED]->(m:Movie)
        WHERE toLower(m.title) CONTAINS toLower($term)
        RETURN p.name AS director,
               m.title AS movie,
               m.released AS year
        LIMIT 20
    """,

    "recommend": """
        MATCH (m:Movie)
        WHERE toLower(m.title) CONTAINS toLower($term)
        MATCH (m)<-[:ACTED_IN]-(p:Person)-[:ACTED_IN]->(other:Movie)
        WHERE other <> m
        RETURN other.title AS title,
               other.released AS year,
               collect(DISTINCT p.name) AS shared_actors,
               count(DISTINCT p) AS connection_count
        ORDER BY connection_count DESC
        LIMIT 8
    """
}

def route(question):
    text = question.lower().strip()
    patterns = [
        ("recommend", [
            r"recommend movies like (.+)",
            r"recommend (.+)",
            r"movies like (.+)",
            r"films like (.+)",
            r"similar to (.+)"
        ]),
        ("role", [
            r"who voiced (.+)",
            r"who played (.+)",
            r"who portrayed (.+)"
        ]),
        ("director", [
            r"who directed (.+)",
            r"director of (.+)"
        ]),
        ("cast", [
            r"who acted in (.+)",
            r"cast of (.+)",
            r"actors in (.+)",
            r"who is in (.+)"
        ]),
        ("actor", [
            r"what movies did (.+?) act in",
            r"which movies did (.+?) act in",
            r"what films did (.+?) act in",
            r"filmography of (.+)"
        ]),
        ("movie", [
            r"tell me about (.+)",
            r"details (?:of|about) (.+)",
            r"information (?:on|about) (.+)"
        ])
    ]
    for intent, regexes in patterns:
        for pattern in regexes:
            match = re.search(pattern, text)
            if match:
                term = match.group(1).strip(" ?.!\"'")
                return intent, term
    return "movie", text.strip(" ?.!\"'")

def ask_cinegraph(question):
    intent, term = route(question)
    try:
        with driver.session() as session:
            records = [record.data() for record in session.run(QUERIES[intent], {"term": term})]
    except Exception as e:
        return f"Neo4j query failed: {str(e)}", intent, term, []

    if not records:
        return ("No matching graph evidence was found. Try a different query.", intent, term, [])

    prompt = (
        "Answer the question using ONLY the Neo4j evidence below. "
        "Do not invent facts. If the evidence is incomplete, say so. "
        "For recommendations, explain that shared actors are the basis "
        "for the recommendation.\n\n"
        f"Question: {question}\n"
        f"Evidence: {records}"
    )

    try:
        response = gemini.models.generate_content(model=MODEL, contents=prompt)
        answer = (response.text or "").strip()
        if not answer:
            answer = "Gemini returned an empty response."
    except Exception as e:
        answer = f"Gemini unavailable ({type(e).__name__}); inspect retrieved evidence below."

    return answer, intent, term, records

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🎬 CineGraph</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #111827, #0f172a);
            color: #f1f5f9;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        .header {
            background: linear-gradient(120deg, #1e293b, #312e81);
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            margin-bottom: 25px;
            text-align: center;
        }
        h1 { margin: 0; font-size: 2.5rem; color: #38bdf8; }
        .subtitle { color: #94a3b8; font-size: 1.1rem; margin-top: 5px; }
        .grid {
            display: grid;
            grid-template-columns: 1fr 3fr;
            gap: 20px;
        }
        .sidebar {
            background: #1e293b;
            padding: 20px;
            border-radius: 10px;
            height: fit-content;
        }
        .sidebar h3 { margin-top: 0; color: #38bdf8; }
        .suggested-btn {
            display: block;
            width: 100%;
            text-align: left;
            background: #334155;
            color: #f1f5f9;
            border: none;
            padding: 10px 12px;
            margin-bottom: 8px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.2s;
        }
        .suggested-btn:hover { background: #475569; }
        .main-panel {
            background: #1e293b;
            padding: 25px;
            border-radius: 10px;
        }
        .input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input[type="text"] {
            flex: 1;
            padding: 12px;
            font-size: 1rem;
            border-radius: 6px;
            border: 1px solid #475569;
            background: #0f172a;
            color: #f1f5f9;
        }
        button[type="submit"] {
            background: #0284c7;
            color: white;
            border: none;
            padding: 12px 24px;
            font-weight: bold;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button[type="submit"]:hover { background: #0369a1; }
        .answer-box {
            background: #0f172a;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #38bdf8;
            margin-top: 20px;
            line-height: 1.6;
        }
        .metrics {
            display: flex;
            gap: 15px;
            margin: 20px 0;
        }
        .metric-card {
            background: #334155;
            padding: 10px 15px;
            border-radius: 6px;
            flex: 1;
            text-align: center;
        }
        .metric-title { font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }
        .metric-value { font-size: 1.2rem; font-weight: bold; margin-top: 4px; color: #38bdf8; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            background: #0f172a;
            border-radius: 6px;
            overflow: hidden;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }
        th { background: #334155; color: #38bdf8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 CineGraph</h1>
            <div class="subtitle">Graph Retrieval &bull; Evidence First &bull; Flask Engine</div>
        </div>

        <div class="grid">
            <div class="sidebar">
                <h3>Try a Suggestion</h3>
                <button class="suggested-btn" onclick="setQuestion('Tell me about Toy Story')">Tell me about Toy Story</button>
                <button class="suggested-btn" onclick="setQuestion('Who acted in Toy Story?')">Who acted in Toy Story?</button>
                <button class="suggested-btn" onclick="setQuestion('What movies did Tom Hanks act in?')">What movies did Tom Hanks act in?</button>
                <button class="suggested-btn" onclick="setQuestion('Who voiced Woody?')">Who voiced Woody?</button>
                <button class="suggested-btn" onclick="setQuestion('Who directed The Matrix?')">Who directed The Matrix?</button>
                <button class="suggested-btn" onclick="setQuestion('Recommend movies like Heat')">Recommend movies like Heat</button>
            </div>

            <div class="main-panel">
                <form method="POST" action="/">
                    <div class="input-group">
                        <input type="text" name="question" id="qInput" placeholder="For example: Who voiced Woody?" value="{{ question }}" required>
                        <button type="submit">Find Answer</button>
                    </div>
                </form>

                {% if answer %}
                    <div class="metrics">
                        <div class="metric-card">
                            <div class="metric-title">Query Type</div>
                            <div class="metric-value">{{ intent|upper }}</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-title">Search Term</div>
                            <div class="metric-value">{{ term }}</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-title">Records Found</div>
                            <div class="metric-value">{{ records|length }}</div>
                        </div>
                    </div>

                    <h3>Answer</h3>
                    <div class="answer-box">
                        {{ answer }}
                    </div>

                    {% if records %}
                        <h3>Retrieved Graph Evidence</h3>
                        <div style="overflow-x:auto;">
                            <table>
                                <thead>
                                    <tr>
                                        {% for key in records[0].keys() %}
                                            <th>{{ key|capitalize }}</th>
                                        {% endfor %}
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for row in records %}
                                        <tr>
                                            {% for val in row.values() %}
                                                <td>{{ val }}</td>
                                            {% endfor %}
                                        </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    {% endif %}
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        function setQuestion(text) {
            document.getElementById('qInput').value = text;
        }
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    question = ""
    answer = ""
    intent = ""
    term = ""
    records = []
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            answer, intent, term, records = ask_cinegraph(question)
    return render_template_string(HTML_TEMPLATE, question=question, answer=answer, intent=intent, term=term, records=records)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
