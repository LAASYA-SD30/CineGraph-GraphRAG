# CineGraph — Graph-Based RAG for Movie Question Answering

## Overview

CineGraph is a graph-based Retrieval-Augmented Generation (RAG) application that uses the Neo4j Movies knowledge graph to answer movie-related questions.

The application retrieves relevant information using Cypher queries and uses Google's Gemini LLM to generate natural-language answers grounded in the retrieved graph evidence.

## Technologies Used

- Python
- Neo4j AuraDB
- Cypher Query Language
- Flask
- Google Gemini API
- Pandas

## Architecture

User Question → Query Classification → Cypher Retrieval → Neo4j Knowledge Graph → Retrieved Evidence → Gemini LLM → Natural-Language Answer

## Demonstrated Queries

1. Who voiced Woody?
2. Who acted in Toy Story?
3. Who directed The Matrix?

The application displays the generated answer and the corresponding retrieved graph evidence.

## Setup

1. Clone this repository.
2. Install the dependencies using `pip install -r requirements.txt`.
3. Configure the following environment variables:
   - `NEO4J_URI`
   - `NEO4J_USERNAME`
   - `NEO4J_PASSWORD`
   - `GEMINI_API_KEY`
4. Run the Flask application using the command appropriate for the application entry-point file.

## Security

Do not commit API keys, database passwords, or other credentials to the repository.

## Future Enhancements

- Improved natural-language question interpretation
- More robust movie recommendations
- Expanded graph retrieval
- Automated evaluation and answer validation
