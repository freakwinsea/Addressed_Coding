with open('experiments/data/log.txt', 'r', encoding='utf-8') as f:
    for line in f:
        if 'ERROR' in line:
            print(line.rstrip('\r\n'))
