/*
Copyright 2012-2020 Ronald Römer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

#ifndef __Merger_h
#define __Merger_h

#include <vector>
#include <map>

#include "VisPoly.h"

typedef std::vector<PolyType> PolysType;

typedef std::map<Pair, double> ConsType;
typedef std::map<int, ConsType> ResType;

class G {
public:
    G (double _d, Pair _con) : d(_d), con(_con) {}
    double d;
    Pair con;
};

class Merger {
    PolysType polys;

    void Merge (PolysType &group, PolyType &merged);

public:
    Merger () {}
    void AddPoly (PolyType &poly);
    void GetMerged (PolysType &res);
};

#endif
