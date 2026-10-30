// Qt 6.8.3's proxy iterators do not meet libc++ 23's sorting requirements.
// Sort owned values, then write them back through the original typed container's iterator.
#pragma once
#include <QtCore/qsequentialiterable.h>
#include <algorithm>
#include <vector>

namespace GowQtCompat {
template<class Compare>
void sortSequence(QSequentialIterable &iterable, const Compare &compare)
{
    std::vector<QVariant> values;
    for (auto it = iterable.mutableBegin(), end = iterable.mutableEnd(); it != end; ++it)
        values.push_back(QVariant(*it));
    std::sort(values.begin(), values.end(), compare);
    auto output = iterable.mutableBegin();
    for (const QVariant &value : values) {
        *output = value;
        ++output;
    }
}
}
