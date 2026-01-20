# block-blast-ai-training
Block blast game + ai that training to play it

Files:
pieces.py - Describes all game pieces using coordinate-based shapes.
game.py - Contains the full game logic (board state, placement rules, scoring, combos, game over conditions).
config.py - Stores game configuration such as board width/height, colors, sizes, and other constants.
state_io.py - Handles writing the current game state to a file (state.json) for the AI to read.
ui.py - Manages the game UI, user interaction, rendering, and connects all core modules together.
main.py - Entry point of the application. Initializes and runs the game loop.
ai.py - AI agent that plays the game using weights loaded from weights.json.
ai_trainer.py - Trains the AI using a population-based (evolutionary) approach and updates the weights.
best_weights.json - Stores the best-performing AI weights found during training.


How to use:
Run main.py using python 3.12 because of pygame, thaт in separate terminal run ai.py and write command on.
