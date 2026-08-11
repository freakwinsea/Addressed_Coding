with open('experiments/data/numbers.txt', 'r', encoding='utf-8') as f:
    numbers = [int(line) for line in f if line.strip()]
mean = int(sum(numbers) / len(numbers))
print(mean)
