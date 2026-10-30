// Validate the Qt 6.8.3 / libc++ 23 sequence-sort compatibility adjustment in modules/qt.ps1.
#include "../pipeline/compat/qt-sequence-sort.h"
#include <QtCore/qlist.h>
#include <algorithm>
#include <iostream>
#include <random>
#include <list>
#include <vector>

template<class Container, class Compare>
bool check(Container values, Compare compare)
{
    std::vector<int> expected(values.begin(), values.end());
    std::sort(expected.begin(), expected.end(), compare);
    QSequentialIterable iterable(&values);
    GowQtCompat::sortSequence(iterable,
                            [&](const QVariant &a, const QVariant &b) { return compare(a.toInt(), b.toInt()); });
    return std::equal(expected.begin(), expected.end(), values.begin(), values.end());
}

int main()
{
    std::mt19937 random(28);
    for (int size : {0, 1, 2, 16, 128, 1024}) {
        QList<int> values;
        for (int i = 0; i < size; ++i) values.append(int(random() % 31));
        const std::list<int> linked(values.begin(), values.end());
        if (!check(values, std::less<int>{}) || !check(values, std::greater<int>{})
            || !check(linked, std::less<int>{}) || !check(linked, std::greater<int>{})) {
            std::cerr << "Qt sequence sort failed at size " << size << '\n';
            return 1;
        }
    }
    std::cout << "PASS: 24 Qt sequence sorting cases (empty, duplicates, ascending and descending)\n";
}
