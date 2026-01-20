import json
import random
from copy import deepcopy

STATS_FILE = "stats.json"
WEIGHTS_FILE = "weights.json"
BEST_FILE = "best_weights.json"
POPULATION_FILE = "population.json"
CURRENT_INDEX_FILE = "current_index.json"

POPULATION_SIZE = 10
TOP_KEEP = 2
MUTATE_RATE = 0.2
MUTATE_POWER = 0.25

BOUNDS = {
    'holes': (-15, -1),
    'max_height': (-8, -0.5),
    'avg_height': (-5, -0.1),
    'filled': (-2, 0),
    'edge_penalty': (-5, 0),
    'cluster_score': (0, 10),
    'row_almost_full': (5, 30),
    'col_almost_full': (5, 30),
    'empty_rows': (0, 15),
    'combo_preservation': (20, 100),
    'piece_fit': (2, 20),
    'diversity': (0, 10),
    'cleared_lines': (50, 200),
    'immediate_gain': (0, 5),
}


def load_json(path):
    """Безпечно завантажує JSON файл."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def save_json(path, data):
    """Зберігає дані у JSON файл."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def calc_fitness(stats):
    """Розраховує fitness метрику на основі статистики ігор."""
    if not stats:
        return 0
    games = list(stats.values())
    moves = sum(g['Moves'] for g in games) / len(games)
    score = sum(g['Score'] for g in games) / len(games)
    combo = sum(g['Max_Combo'] for g in games) / len(games)
    return moves + combo * 0.4 + score * 0.001


def random_weights():
    """Генерує випадкові ваги в межах визначених bounds."""
    return {k: random.uniform(v[0], v[1]) for k, v in BOUNDS.items()}


def mutate(w):
    """Застосовує мутацію до ваг."""
    new = w.copy()
    for k in new:
        if random.random() < MUTATE_RATE:
            mn, mx = BOUNDS[k]
            delta = (mx - mn) * MUTATE_POWER
            new[k] += random.uniform(-delta, delta)
            new[k] = max(mn, min(mx, new[k]))
    return new


def crossover(w1, w2):
    """Виконує кросовер між двома наборами ваг."""
    return {k: w1[k] if random.random() < 0.5 else w2[k] for k in w1}


def train():
    """Головна функція тренування генетичного алгоритму."""
    stats = load_json(STATS_FILE)
    if not stats:
        return
    
    population = load_json(POPULATION_FILE)
    current_idx = load_json(CURRENT_INDEX_FILE)
    
    if not population:
        current_weights = load_json(WEIGHTS_FILE) or random_weights()
        population = [{'w': random_weights(), 'f': 0} for _ in range(POPULATION_SIZE)]
        population[0]['w'] = current_weights
        current_idx = 0
    
    if current_idx is None:
        current_idx = 0
    
    fitness = calc_fitness(stats)
    population[current_idx]['f'] = fitness
    
    all_evaluated = all(p['f'] > 0 for p in population)
    
    if all_evaluated:
        population.sort(key=lambda x: x['f'], reverse=True)
        
        best_data = load_json(BEST_FILE)
        if best_data is None:
            best_fitness = 0
        else:
            if isinstance(best_data, dict) and 'f' not in best_data:
                best_fitness = 0
            else:
                best_fitness = best_data.get('f', 0)
        
        if population[0]['f'] > best_fitness:
            print(f"🎉 Новий рекорд! Fitness: {population[0]['f']:.2f} (було {best_fitness:.2f})")
            save_json(BEST_FILE, {
                'w': population[0]['w'],
                'f': population[0]['f']
            })
        
        new_pop = [deepcopy(p) for p in population[:TOP_KEEP]]
        
        while len(new_pop) < POPULATION_SIZE:
            p1 = random.choice(population[:POPULATION_SIZE//2])
            p2 = random.choice(population[:POPULATION_SIZE//2])
            child = {'w': mutate(crossover(p1['w'], p2['w'])), 'f': 0}
            new_pop.append(child)
        
        population = new_pop
        current_idx = 0
    else:
        current_idx += 1
        while current_idx < len(population) and population[current_idx]['f'] > 0:
            current_idx += 1
        
        if current_idx >= len(population):
            current_idx = 0
    
    save_json(POPULATION_FILE, population)
    save_json(CURRENT_INDEX_FILE, current_idx)
    save_json(WEIGHTS_FILE, population[current_idx]['w'])


if __name__ == "__main__":
    train()