def calculate_integral_score(results):
    score = 0
    for i in range(len(results) - 1):
        score += (results[i] + results[i + 1]) / 2
    return score
