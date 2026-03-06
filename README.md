# Sim CO

## Frontend
Phaser + Vanilla JS

## Basic Setup:

Clone this repo and open index.html with Live Server (no installation needed 🙂)

Open index.html, add a character,

## Current Features:

Agents talk to each other ( rn it s hi), and when the game is on, they go to the prize and can pick money.

## How do they do it?

### Rule-based state machine + memory !!!!

Agents use BFS to move toward a target.
The target can be another agent or the prize.

For now us ( humans) choose how much money they take, and can help when they dont see the path ( minor bug)