#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "DGtal/helpers/StdDefs.h"
#include "DGtal/io/readers/SurfaceMeshReader.h"
#include "DGtal/shapes/Mesh.h"
#include "DGtal/shapes/MeshVoxelizer.h"
#include "DGtal/topology/NeighborhoodConfigurations.h"
#include "DGtal/topology/VoxelComplex.h"
#include "DGtal/topology/VoxelComplexThinning.h"

namespace {

using Point = DGtal::Z3i::Point;
using RealPoint = DGtal::Z3i::RealPoint;
using RealVector = DGtal::Z3i::RealVector;
using Domain = DGtal::Z3i::Domain;
using DigitalSet = DGtal::Z3i::DigitalSet;
using Complex = DGtal::VoxelComplex<DGtal::Z3i::KSpace>;

struct Options {
  std::string input_mesh;
  std::string output_csv;
  std::string mode = "single";
  double voxel_size = 0.1;
  int max_grid_size = 192;
  int persistence = 0;
  int min_component_voxels = 4;
  int min_path_points = 2;
  double min_path_length = 0.75;
  int min_cycle_length = 8;
  bool one_isthmus = false;
};

struct CenterlinePath {
  std::size_t component_id = 0;
  std::vector<std::size_t> cells;
};

struct GraphEdge {
  std::size_t first = 0;
  std::size_t second = 0;
  double weight = 0.0;
};

class DisjointSet {
 public:
  explicit DisjointSet(std::size_t size) : parent_(size), rank_(size, 0) {
    for (std::size_t index = 0; index < size; ++index) {
      parent_[index] = index;
    }
  }

  std::size_t find(std::size_t value) {
    if (parent_[value] != value) {
      parent_[value] = find(parent_[value]);
    }
    return parent_[value];
  }

  bool unite(std::size_t first, std::size_t second) {
    first = find(first);
    second = find(second);
    if (first == second) {
      return false;
    }
    if (rank_[first] < rank_[second]) {
      std::swap(first, second);
    }
    parent_[second] = first;
    if (rank_[first] == rank_[second]) {
      ++rank_[first];
    }
    return true;
  }

 private:
  std::vector<std::size_t> parent_;
  std::vector<unsigned char> rank_;
};

struct Grid {
  int nx = 0;
  int ny = 0;
  int nz = 0;

  std::size_t index(int x, int y, int z) const {
    return (static_cast<std::size_t>(z) * static_cast<std::size_t>(ny) +
            static_cast<std::size_t>(y)) * static_cast<std::size_t>(nx) +
           static_cast<std::size_t>(x);
  }

  std::size_t index(const Point& point) const {
    return index(point[0], point[1], point[2]);
  }

  Point point(std::size_t value) const {
    const int x = static_cast<int>(value % static_cast<std::size_t>(nx));
    const std::size_t yz = value / static_cast<std::size_t>(nx);
    const int y = static_cast<int>(yz % static_cast<std::size_t>(ny));
    const int z = static_cast<int>(yz / static_cast<std::size_t>(ny));
    return Point(x, y, z);
  }

  std::size_t cell_count() const {
    return static_cast<std::size_t>(nx) * static_cast<std::size_t>(ny) *
           static_cast<std::size_t>(nz);
  }
};

struct Bounds {
  RealPoint lower;
  RealPoint upper;
};

void print_usage(const char* program) {
  std::cerr << "Usage: " << program
            << " <input_mesh.obj> <output.csv> [--voxel-size SIZE]"
            " [--mode single|network]"
            " [--max-grid-size SIZE] [--persistence N]"
            " [--min-component-voxels N] [--min-path-points N]"
            " [--min-path-length SIZE] [--min-cycle-length N]"
            " [--one-isthmus]\n";
}

double parse_positive_double(const std::string& value, const char* option) {
  const double parsed = std::stod(value);
  if (!std::isfinite(parsed) || parsed <= 0.0) {
    throw std::invalid_argument(std::string(option) + " must be positive");
  }
  return parsed;
}

double parse_nonnegative_double(const std::string& value, const char* option) {
  const double parsed = std::stod(value);
  if (!std::isfinite(parsed) || parsed < 0.0) {
    throw std::invalid_argument(std::string(option) + " must not be negative");
  }
  return parsed;
}

int parse_nonnegative_int(const std::string& value, const char* option) {
  const int parsed = std::stoi(value);
  if (parsed < 0) {
    throw std::invalid_argument(std::string(option) + " must not be negative");
  }
  return parsed;
}

Options parse_options(int argc, char** argv) {
  if (argc < 3) {
    print_usage(argv[0]);
    throw std::invalid_argument("input mesh and output CSV are required");
  }

  Options options{argv[1], argv[2]};
  for (int i = 3; i < argc; ++i) {
    const std::string argument = argv[i];
    if (argument == "--mode" && i + 1 < argc) {
      options.mode = argv[++i];
      if (options.mode != "single" && options.mode != "network") {
        throw std::invalid_argument("--mode must be either 'single' or 'network'");
      }
    } else if (argument == "--voxel-size" && i + 1 < argc) {
      options.voxel_size = parse_positive_double(argv[++i], "--voxel-size");
    } else if (argument == "--max-grid-size" && i + 1 < argc) {
      options.max_grid_size = parse_nonnegative_int(argv[++i], "--max-grid-size");
      if (options.max_grid_size < 16) {
        throw std::invalid_argument("--max-grid-size must be at least 16");
      }
    } else if (argument == "--persistence" && i + 1 < argc) {
      options.persistence = parse_nonnegative_int(argv[++i], "--persistence");
    } else if (argument == "--min-component-voxels" && i + 1 < argc) {
      options.min_component_voxels =
          parse_nonnegative_int(argv[++i], "--min-component-voxels");
      if (options.min_component_voxels < 1) {
        throw std::invalid_argument("--min-component-voxels must be at least 1");
      }
    } else if (argument == "--min-path-points" && i + 1 < argc) {
      options.min_path_points =
          parse_nonnegative_int(argv[++i], "--min-path-points");
      if (options.min_path_points < 2) {
        throw std::invalid_argument("--min-path-points must be at least 2");
      }
    } else if (argument == "--min-path-length" && i + 1 < argc) {
      options.min_path_length =
          parse_nonnegative_double(argv[++i], "--min-path-length");
    } else if (argument == "--min-cycle-length" && i + 1 < argc) {
      options.min_cycle_length =
          parse_nonnegative_int(argv[++i], "--min-cycle-length");
      if (options.min_cycle_length < 1) {
        throw std::invalid_argument("--min-cycle-length must be at least 1");
      }
    } else if (argument == "--one-isthmus") {
      options.one_isthmus = true;
    } else if (argument == "--help") {
      print_usage(argv[0]);
      std::exit(0);
    } else {
      print_usage(argv[0]);
      throw std::invalid_argument("unknown or incomplete option: " + argument);
    }
  }
  return options;
}

Bounds mesh_bounds(const DGtal::SurfaceMesh<RealPoint, RealVector>& mesh) {
  if (mesh.positions().empty()) {
    throw std::runtime_error("mesh contains no vertices");
  }

  Bounds bounds{mesh.positions().front(), mesh.positions().front()};
  for (const RealPoint& point : mesh.positions()) {
    bounds.lower = bounds.lower.inf(point);
    bounds.upper = bounds.upper.sup(point);
  }
  return bounds;
}

Grid make_grid(const Bounds& bounds, const Options& options, double& scale,
               double& voxel_size, RealPoint& origin) {
  const double max_span = std::max({bounds.upper[0] - bounds.lower[0],
                                    bounds.upper[1] - bounds.lower[1],
                                    bounds.upper[2] - bounds.lower[2]});
  if (!std::isfinite(max_span) || max_span <= 0.0) {
    throw std::runtime_error("mesh has no positive spatial extent");
  }

  constexpr int padding = 2;
  scale = 1.0 / options.voxel_size;
  const double requested_resolution =
      std::ceil(max_span * scale) + 2 * padding + 1;
  if (requested_resolution > options.max_grid_size) {
    scale = static_cast<double>(options.max_grid_size - 2 * padding - 1) /
            max_span;
  }
  voxel_size = 1.0 / scale;
  origin = bounds.lower;
  for (int dimension = 0; dimension < 3; ++dimension) {
    origin[dimension] -= padding * voxel_size;
  }

  Grid grid;
  grid.nx = static_cast<int>(std::ceil((bounds.upper[0] - origin[0]) * scale)) + 1;
  grid.ny = static_cast<int>(std::ceil((bounds.upper[1] - origin[1]) * scale)) + 1;
  grid.nz = static_cast<int>(std::ceil((bounds.upper[2] - origin[2]) * scale)) + 1;

  if (grid.nx < 3 || grid.ny < 3 || grid.nz < 3) {
    throw std::runtime_error("mesh grid is too small for a closed-volume flood fill");
  }
  if (grid.nx > options.max_grid_size || grid.ny > options.max_grid_size ||
      grid.nz > options.max_grid_size) {
    throw std::runtime_error("computed voxel grid exceeds --max-grid-size");
  }
  if (grid.cell_count() > 100000000ULL) {
    throw std::runtime_error("computed voxel grid is too large; increase voxel size");
  }
  return grid;
}

DGtal::Mesh<RealPoint> make_voxel_mesh(
    const DGtal::SurfaceMesh<RealPoint, RealVector>& source,
    const RealPoint& origin, double scale) {
  DGtal::Mesh<RealPoint> mesh;
  for (const RealPoint& point : source.positions()) {
    RealPoint transformed;
    for (int dimension = 0; dimension < 3; ++dimension) {
      transformed[dimension] = (point[dimension] - origin[dimension]) * scale;
    }
    mesh.addVertex(transformed);
  }

  for (const auto& face : source.allIncidentVertices()) {
    typename DGtal::Mesh<RealPoint>::MeshFace converted_face(face.cbegin(), face.cend());
    if (converted_face.size() >= 3) {
      mesh.addFace(converted_face);
    }
  }
  return mesh;
}

std::vector<std::size_t> neighbours(std::size_t cell, const Grid& grid,
                                    const std::vector<unsigned char>& mask) {
  const Point point = grid.point(cell);
  std::vector<std::size_t> result;
  result.reserve(26);
  for (int dz = -1; dz <= 1; ++dz) {
    for (int dy = -1; dy <= 1; ++dy) {
      for (int dx = -1; dx <= 1; ++dx) {
        if (dx == 0 && dy == 0 && dz == 0) {
          continue;
        }
        const int x = point[0] + dx;
        const int y = point[1] + dy;
        const int z = point[2] + dz;
        if (x >= 0 && x < grid.nx && y >= 0 && y < grid.ny && z >= 0 &&
            z < grid.nz) {
          const std::size_t neighbour = grid.index(x, y, z);
          if (mask[neighbour] != 0) {
            result.push_back(neighbour);
          }
        }
      }
    }
  }
  return result;
}

std::size_t fill_interior(const Grid& grid,
                          const std::vector<unsigned char>& surface,
                          std::vector<unsigned char>& outside) {
  std::deque<std::size_t> queue;
  auto enqueue = [&](int x, int y, int z) {
    const std::size_t cell = grid.index(x, y, z);
    if (surface[cell] == 0 && outside[cell] == 0) {
      outside[cell] = 1;
      queue.push_back(cell);
    }
  };

  for (int z = 0; z < grid.nz; ++z) {
    for (int y = 0; y < grid.ny; ++y) {
      enqueue(0, y, z);
      enqueue(grid.nx - 1, y, z);
    }
  }
  for (int z = 0; z < grid.nz; ++z) {
    for (int x = 0; x < grid.nx; ++x) {
      enqueue(x, 0, z);
      enqueue(x, grid.ny - 1, z);
    }
  }
  for (int y = 0; y < grid.ny; ++y) {
    for (int x = 0; x < grid.nx; ++x) {
      enqueue(x, y, 0);
      enqueue(x, y, grid.nz - 1);
    }
  }

  constexpr std::array<std::array<int, 3>, 6> directions{{
      {{-1, 0, 0}}, {{1, 0, 0}}, {{0, -1, 0}},
      {{0, 1, 0}},  {{0, 0, -1}}, {{0, 0, 1}},
  }};
  while (!queue.empty()) {
    const std::size_t cell = queue.front();
    queue.pop_front();
    const Point point = grid.point(cell);
    for (const auto& direction : directions) {
      const int x = point[0] + direction[0];
      const int y = point[1] + direction[1];
      const int z = point[2] + direction[2];
      if (x >= 0 && x < grid.nx && y >= 0 && y < grid.ny && z >= 0 &&
          z < grid.nz) {
        enqueue(x, y, z);
      }
    }
  }

  std::size_t interior_count = 0;
  for (std::size_t cell = 0; cell < grid.cell_count(); ++cell) {
    if (surface[cell] != 0 || outside[cell] == 0) {
      ++interior_count;
    }
  }
  return interior_count;
}

std::vector<std::vector<std::size_t>> connected_components(
    const Grid& grid, const std::vector<unsigned char>& skeleton) {
  std::vector<unsigned char> visited(grid.cell_count(), 0);
  std::vector<std::vector<std::size_t>> components;
  for (std::size_t start = 0; start < grid.cell_count(); ++start) {
    if (skeleton[start] == 0 || visited[start] != 0) {
      continue;
    }
    std::vector<std::size_t> component;
    std::deque<std::size_t> queue{start};
    visited[start] = 1;
    while (!queue.empty()) {
      const std::size_t cell = queue.front();
      queue.pop_front();
      component.push_back(cell);
      for (const std::size_t neighbour : neighbours(cell, grid, skeleton)) {
        if (visited[neighbour] == 0) {
          visited[neighbour] = 1;
          queue.push_back(neighbour);
        }
      }
    }
    components.push_back(std::move(component));
  }
  return components;
}

std::vector<std::size_t> largest_component(
    const std::vector<std::vector<std::size_t>>& components) {
  std::vector<std::size_t> largest;
  for (const auto& component : components) {
    if (component.size() > largest.size()) {
      largest = component;
    }
  }
  return largest;
}

std::uint64_t edge_key(std::size_t first, std::size_t second,
                       std::size_t cell_count) {
  if (first > second) {
    std::swap(first, second);
  }
  return static_cast<std::uint64_t>(first) *
             static_cast<std::uint64_t>(cell_count) +
         static_cast<std::uint64_t>(second);
}

double path_length(const Grid& grid, const std::vector<std::size_t>& path,
                   double voxel_size) {
  double length = 0.0;
  for (std::size_t index = 1; index < path.size(); ++index) {
    const Point first = grid.point(path[index - 1]);
    const Point second = grid.point(path[index]);
    const double dx = static_cast<double>(first[0] - second[0]);
    const double dy = static_cast<double>(first[1] - second[1]);
    const double dz = static_cast<double>(first[2] - second[2]);
    length += std::sqrt(dx * dx + dy * dy + dz * dz) * voxel_size;
  }
  return length;
}

std::size_t farthest_cell(std::size_t start, const Grid& grid,
                          const std::vector<unsigned char>& mask,
                          std::vector<std::int64_t>* previous) {
  std::vector<int> distance(grid.cell_count(), -1);
  if (previous != nullptr) {
    previous->assign(grid.cell_count(), -1);
  }
  std::deque<std::size_t> queue{start};
  distance[start] = 0;
  std::size_t farthest = start;
  while (!queue.empty()) {
    const std::size_t cell = queue.front();
    queue.pop_front();
    if (distance[cell] > distance[farthest]) {
      farthest = cell;
    }
    for (const std::size_t neighbour : neighbours(cell, grid, mask)) {
      if (distance[neighbour] == -1) {
        distance[neighbour] = distance[cell] + 1;
        if (previous != nullptr) {
          (*previous)[neighbour] = static_cast<std::int64_t>(cell);
        }
        queue.push_back(neighbour);
      }
    }
  }
  return farthest;
}

std::vector<std::size_t> extract_diameter(
    const Grid& grid, const std::vector<unsigned char>& mask,
    const std::vector<std::size_t>& component) {
  if (component.size() < 2) {
    return component;
  }

  const std::size_t first = farthest_cell(component.front(), grid, mask, nullptr);
  std::vector<std::int64_t> previous;
  const std::size_t last = farthest_cell(first, grid, mask, &previous);

  std::vector<std::size_t> path;
  for (std::int64_t current = static_cast<std::int64_t>(last); current >= 0;
       current = previous[static_cast<std::size_t>(current)]) {
    path.push_back(static_cast<std::size_t>(current));
    if (static_cast<std::size_t>(current) == first) {
      break;
    }
  }
  std::reverse(path.begin(), path.end());
  return path;
}

int tree_distance(std::size_t first, std::size_t second,
                  const std::vector<std::size_t>& component,
                  const std::vector<std::size_t>& local_index,
                  const std::vector<std::vector<std::size_t>>& tree_neighbours) {
  std::vector<int> distances(component.size(), -1);
  std::deque<std::size_t> queue;
  const std::size_t start = local_index[first];
  const std::size_t target = local_index[second];
  distances[start] = 0;
  queue.push_back(start);
  while (!queue.empty()) {
    const std::size_t current = queue.front();
    queue.pop_front();
    if (current == target) {
      return distances[current];
    }
    for (const std::size_t neighbour : tree_neighbours[current]) {
      const std::size_t neighbour_index = local_index[neighbour];
      if (distances[neighbour_index] < 0) {
        distances[neighbour_index] = distances[current] + 1;
        queue.push_back(neighbour_index);
      }
    }
  }
  return -1;
}

std::vector<CenterlinePath> extract_network_paths(
    const Grid& grid, const std::vector<unsigned char>& skeleton,
    int min_component_voxels, int min_path_points, double min_path_length,
    double voxel_size, int min_cycle_length,
    std::size_t& selected_component_count,
    std::size_t& total_component_count) {
  const auto components = connected_components(grid, skeleton);
  total_component_count = components.size();
  const std::size_t invalid_index = std::numeric_limits<std::size_t>::max();
  std::vector<std::size_t> local_index(grid.cell_count(), invalid_index);

  std::vector<CenterlinePath> paths;
  selected_component_count = 0;
  for (std::size_t component_id = 0; component_id < components.size();
       ++component_id) {
    const auto& component = components[component_id];
    if (component.size() < static_cast<std::size_t>(min_component_voxels)) {
      continue;
    }
    ++selected_component_count;

    for (std::size_t index = 0; index < component.size(); ++index) {
      local_index[component[index]] = index;
    }

    std::vector<GraphEdge> edges;
    edges.reserve(component.size() * 3);
    for (const std::size_t cell : component) {
      for (const std::size_t neighbour : neighbours(cell, grid, skeleton)) {
        if (cell >= neighbour || local_index[neighbour] == invalid_index) {
          continue;
        }
        const Point first = grid.point(cell);
        const Point second = grid.point(neighbour);
        const double dx = static_cast<double>(first[0] - second[0]);
        const double dy = static_cast<double>(first[1] - second[1]);
        const double dz = static_cast<double>(first[2] - second[2]);
        edges.push_back({cell, neighbour, dx * dx + dy * dy + dz * dz});
      }
    }
    std::sort(edges.begin(), edges.end(), [](const GraphEdge& first,
                                             const GraphEdge& second) {
      if (first.weight != second.weight) {
        return first.weight < second.weight;
      }
      if (first.first != second.first) {
        return first.first < second.first;
      }
      return first.second < second.second;
    });

    std::vector<std::vector<std::size_t>> graph_neighbours(component.size());
    DisjointSet disjoint_set(component.size());
    std::unordered_set<std::uint64_t> tree_edges;
    tree_edges.reserve(component.size() * 2);
    for (const GraphEdge& edge : edges) {
      const std::size_t first = local_index[edge.first];
      const std::size_t second = local_index[edge.second];
      if (disjoint_set.unite(first, second)) {
        graph_neighbours[first].push_back(edge.second);
        graph_neighbours[second].push_back(edge.first);
        tree_edges.insert(edge_key(edge.first, edge.second, grid.cell_count()));
      }
    }
    for (const GraphEdge& edge : edges) {
      const std::uint64_t key = edge_key(edge.first, edge.second,
                                         grid.cell_count());
      if (tree_edges.find(key) != tree_edges.end()) {
        continue;
      }
      const int cycle_distance = tree_distance(
          edge.first, edge.second, component, local_index, graph_neighbours);
      if (cycle_distance >= min_cycle_length) {
        const std::size_t first = local_index[edge.first];
        const std::size_t second = local_index[edge.second];
        graph_neighbours[first].push_back(edge.second);
        graph_neighbours[second].push_back(edge.first);
      }
    }

    std::unordered_set<std::uint64_t> visited_edges;
    visited_edges.reserve(component.size() * 2);
    auto mark_edge = [&](std::size_t first, std::size_t second) {
      return visited_edges.insert(edge_key(first, second, grid.cell_count()))
          .second;
    };

    if (component.size() >= 2) {
      bool has_node = false;
      for (const auto& neighbours_for_cell : graph_neighbours) {
        if (neighbours_for_cell.size() != 2) {
          has_node = true;
          break;
        }
      }

      if (!has_node) {
        const std::size_t start = component.front();
        const auto& start_neighbours = graph_neighbours.front();
        if (!start_neighbours.empty()) {
          std::vector<std::size_t> cycle{start};
          std::size_t previous = start;
          std::size_t current = start_neighbours.front();
          mark_edge(previous, current);
          while (current != start && cycle.size() <= component.size() + 1) {
            cycle.push_back(current);
            const std::size_t current_index = local_index[current];
            std::size_t next = current;
            for (const std::size_t candidate :
                 graph_neighbours[current_index]) {
              if (candidate != previous &&
                  visited_edges.find(edge_key(current, candidate,
                                              grid.cell_count())) ==
                      visited_edges.end()) {
                next = candidate;
                break;
              }
            }
            if (next == current || !mark_edge(current, next)) {
              break;
            }
            previous = current;
            current = next;
          }
          if (cycle.size() >= static_cast<std::size_t>(min_path_points) &&
              path_length(grid, cycle, voxel_size) >= min_path_length) {
            paths.push_back({component_id, std::move(cycle)});
          }
        }
      } else {
        for (std::size_t node_index = 0; node_index < component.size();
             ++node_index) {
          if (graph_neighbours[node_index].size() == 2) {
            continue;
          }
          const std::size_t node = component[node_index];
          for (const std::size_t neighbour : graph_neighbours[node_index]) {
            if (visited_edges.find(edge_key(node, neighbour,
                                            grid.cell_count())) !=
                visited_edges.end()) {
              continue;
            }
            mark_edge(node, neighbour);
            std::vector<std::size_t> path{node};
            std::size_t previous = node;
            std::size_t current = neighbour;
            while (true) {
              path.push_back(current);
              const std::size_t current_index = local_index[current];
              if (graph_neighbours[current_index].size() != 2) {
                break;
              }
              std::size_t next = current;
              for (const std::size_t candidate :
                   graph_neighbours[current_index]) {
                if (candidate != previous) {
                  next = candidate;
                  break;
                }
              }
              if (next == current || !mark_edge(current, next)) {
                break;
              }
              previous = current;
              current = next;
            }
            if (path.size() >= static_cast<std::size_t>(min_path_points) &&
                path_length(grid, path, voxel_size) >= min_path_length) {
              paths.push_back({component_id, std::move(path)});
            }
          }
        }
      }
    }
    for (const std::size_t cell : component) {
      local_index[cell] = invalid_index;
    }
  }
  return paths;
}

void write_centerline_network(const std::string& output_path, const Grid& grid,
                      const std::vector<CenterlinePath>& paths,
                      const RealPoint& origin, double voxel_size) {
  std::ofstream output(output_path);
  if (!output) {
    throw std::runtime_error("cannot open output CSV: " + output_path);
  }
  output << "branch_id,component_id,x,y,z\n";
  output << std::setprecision(12);
  for (std::size_t branch_id = 0; branch_id < paths.size(); ++branch_id) {
    for (const std::size_t cell : paths[branch_id].cells) {
      const Point point = grid.point(cell);
      output << branch_id << "," << paths[branch_id].component_id << ","
             << origin[0] + (static_cast<double>(point[0]) + 0.5) * voxel_size
             << ","
             << origin[1] + (static_cast<double>(point[1]) + 0.5) * voxel_size
             << ","
             << origin[2] + (static_cast<double>(point[2]) + 0.5) * voxel_size
             << "\n";
    }
  }
  if (!output || paths.empty()) {
    throw std::runtime_error("centerline network contains no valid paths");
  }
}

void write_centerline_single(const std::string& output_path, const Grid& grid,
                             const std::vector<std::size_t>& path,
                             const RealPoint& origin, double voxel_size) {
  std::ofstream output(output_path);
  if (!output) {
    throw std::runtime_error("cannot open output CSV: " + output_path);
  }
  output << "x,y,z\n";
  output << std::setprecision(12);
  for (const std::size_t cell : path) {
    const Point point = grid.point(cell);
    output << origin[0] + (static_cast<double>(point[0]) + 0.5) * voxel_size
           << "," << origin[1] + (static_cast<double>(point[1]) + 0.5) * voxel_size
           << "," << origin[2] + (static_cast<double>(point[2]) + 0.5) * voxel_size
           << "\n";
  }
  if (!output || path.size() < 2) {
    throw std::runtime_error("centerline output contains fewer than two points");
  }
}

}

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    if (!std::filesystem::is_regular_file(options.input_mesh)) {
      throw std::runtime_error("input mesh does not exist: " + options.input_mesh);
    }

    std::ifstream input(options.input_mesh);
    DGtal::SurfaceMesh<RealPoint, RealVector> surface_mesh;
    if (!DGtal::SurfaceMeshReader<RealPoint, RealVector>::readOBJ(input,
                                                                   surface_mesh)) {
      throw std::runtime_error("DGtal could not read OBJ mesh: " + options.input_mesh);
    }
    if (surface_mesh.nbFaces() == 0) {
      throw std::runtime_error("mesh contains no faces");
    }

    const Bounds bounds = mesh_bounds(surface_mesh);
    double scale = 0.0;
    double voxel_size = 0.0;
    RealPoint origin;
    const Grid grid = make_grid(bounds, options, scale, voxel_size, origin);
    std::cerr << "centerline: mesh vertices=" << surface_mesh.nbVertices()
              << " faces=" << surface_mesh.nbFaces() << "\n"
              << "centerline: grid=" << grid.nx << "x" << grid.ny << "x" << grid.nz
              << " voxel_size=" << voxel_size << "\n";

    const DGtal::Mesh<RealPoint> voxel_mesh = make_voxel_mesh(surface_mesh, origin, scale);
    const Point lower(0, 0, 0);
    const Point upper(grid.nx - 1, grid.ny - 1, grid.nz - 1);
    const Domain domain(lower, upper);
    DigitalSet surface(domain);
    DGtal::MeshVoxelizer<DigitalSet, 6> voxelizer;
    voxelizer.voxelize(surface, voxel_mesh);
    if (surface.empty()) {
      throw std::runtime_error("mesh voxelization produced no surface voxels");
    }

    std::vector<unsigned char> surface_mask(grid.cell_count(), 0);
    for (const Point& point : surface) {
      surface_mask[grid.index(point)] = 1;
    }
    std::vector<unsigned char> outside(grid.cell_count(), 0);
    const std::size_t solid_count = fill_interior(grid, surface_mask, outside);
    if (solid_count == 0) {
      throw std::runtime_error(
          "mesh does not enclose a voxel volume at the selected resolution");
    }
    std::cerr << "centerline: solid voxels=" << solid_count << "\n";

    DigitalSet solid(domain);
    for (std::size_t cell = 0; cell < grid.cell_count(); ++cell) {
      if (surface_mask[cell] != 0 || outside[cell] == 0) {
        solid.insert(grid.point(cell));
      }
    }

    DGtal::Z3i::KSpace kspace;
    kspace.init(lower, upper, true);
    Complex complex(kspace);
    complex.construct(solid);

    const std::string table_directory = "/usr/local/include/DGtal/topology/tables";
    const std::string simplicity_table = table_directory + "/simplicity_table26_6.zlib";
    if (std::filesystem::is_regular_file(simplicity_table)) {
      const auto table = DGtal::functions::loadTable(simplicity_table);
      complex.setSimplicityTable(*table);
    }

    const auto isthmus_table = DGtal::functions::loadTable(
        table_directory + "/isthmusicity_table26_6.zlib");
    const auto point_map =
        *DGtal::functions::mapZeroPointNeighborhoodToConfigurationMask<Point>();
    std::function<bool(const Complex&, const Complex::Cell&)> skeleton_predicate;
    if (options.one_isthmus) {
      // Preserve only 1D isthmuses: collapses medial sheets into curves,
      // which avoids bushy junction blobs in the skeleton graph.
      skeleton_predicate = [](const Complex& current, const Complex::Cell& cell) {
        return DGtal::functions::oneIsthmus<Complex>(current, cell);
      };
    } else {
      skeleton_predicate = [&isthmus_table, &point_map](
                               const Complex& current,
                               const Complex::Cell& cell) {
        return DGtal::functions::skelWithTable(*isthmus_table, point_map, current,
                                               cell);
      };
    }

    using Metric = DGtal::ExactPredicateLpSeparableMetric<DGtal::Z3i::Space, 3>;
    using DistanceTransform =
        DGtal::DistanceTransformation<DGtal::Z3i::Space, DigitalSet, Metric>;
    DigitalSet distance_set(domain);
    complex.dumpVoxels(distance_set);
    const Metric metric;
    const DistanceTransform distance_transform(domain, distance_set, metric);
    auto deterministic_select = [&distance_transform](const Complex::Clique& clique) {
      auto selected = clique.begin(3);
      if (selected == clique.end(3)) {
        throw std::runtime_error("DGtal supplied an empty critical clique");
      }
      auto selected_value =
          distance_transform(clique.space().uCoords(selected->first));
      for (auto it = clique.begin(3); it != clique.end(3); ++it) {
        const auto value = distance_transform(clique.space().uCoords(it->first));
        if (value > selected_value ||
            (value == selected_value && it->first < selected->first)) {
          selected = it;
          selected_value = value;
        }
      }
      return *selected;
    };

    Complex skeleton_complex(kspace);
    if (options.persistence == 0) {
      skeleton_complex = DGtal::functions::asymetricThinningScheme<Complex>(
          complex, deterministic_select, skeleton_predicate);
    } else {
      skeleton_complex = DGtal::functions::persistenceAsymetricThinningScheme<Complex>(
          complex, deterministic_select, skeleton_predicate,
          options.persistence);
    }
    DigitalSet skeleton_set(domain);
    skeleton_complex.dumpVoxels(skeleton_set);
    if (skeleton_set.empty()) {
      throw std::runtime_error("DGtal thinning produced an empty skeleton");
    }

    std::vector<unsigned char> skeleton_mask(grid.cell_count(), 0);
    for (const Point& point : skeleton_set) {
      skeleton_mask[grid.index(point)] = 1;
    }
    if (options.mode == "single") {
      const auto components = connected_components(grid, skeleton_mask);
      const auto component = largest_component(components);
      if (component.size() < 2) {
        throw std::runtime_error("largest skeleton component contains fewer than two voxels");
      }
      std::vector<unsigned char> component_mask(grid.cell_count(), 0);
      for (const std::size_t cell : component) {
        component_mask[cell] = 1;
      }
      const std::vector<std::size_t> path = extract_diameter(
          grid, component_mask, component);
      std::cerr << "centerline: skeleton voxels=" << skeleton_set.size()
                << " components=" << components.size()
                << " largest_component=" << component.size()
                << " path_points=" << path.size() << "\n";
      write_centerline_single(options.output_csv, grid, path, origin, voxel_size);
    } else {
      std::size_t selected_component_count = 0;
      std::size_t total_component_count = 0;
      const std::vector<CenterlinePath> paths = extract_network_paths(
          grid, skeleton_mask, options.min_component_voxels,
          options.min_path_points, options.min_path_length, voxel_size,
          options.min_cycle_length, selected_component_count,
          total_component_count);
      std::cerr << "centerline: skeleton voxels=" << skeleton_set.size()
                << " components=" << total_component_count
                << " selected_components=" << selected_component_count
                << " network_paths=" << paths.size() << "\n";
      write_centerline_network(options.output_csv, grid, paths, origin, voxel_size);
    }
    std::cerr << "centerline: wrote " << options.output_csv << "\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "centerline: error: " << error.what() << "\n";
    return 1;
  }
}