with open('experiments/data/words.txt', 'r', encoding='utf-8') as f:
    words = f.read().split()
longest_word = max(words, key=len)
print(longest_word)
