from collections import defaultdict

filename = "logs.txt"


def count_loglevel():
    with open(filename, "r") as f:
        m = defaultdict(int)
        for line in f:
            # pass
            # print(line)
            m[line.split()[2]] += 1

        # counts = Counter(line.split()[2] for line in f)

    print(m)
