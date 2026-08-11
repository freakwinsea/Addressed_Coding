lines_written = 0
with open('experiments/data/log.txt', 'r', encoding='utf-8') as fin:
    with open('experiments/out/errors.txt', 'w', encoding='utf-8', newline='\n') as fout:
        for line in fin:
            if 'ERROR' in line:
                fout.write(line.rstrip('\r\n') + '\n')
                lines_written += 1
print(lines_written)
