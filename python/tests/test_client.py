# Copyright (c) 2022, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import subprocess
from pathlib import Path
import time

import pytest

_this_dir = Path(__file__).parent

_data = {"karate": {"csv_file_name":
                    (_this_dir/"karate.csv").absolute().as_posix(),
                    "dtypes": ["int32", "int32", "float32"],
                    "num_edges": 156,
                    },
         }


###############################################################################
## fixtures

@pytest.fixture(scope="module")
def server():
    from gaas_server import server
    server_file = server.__file__
    server_process = None

    with subprocess.Popen([sys.executable, server_file],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          text=True) as server_process:
        try:
            print("\nLaunched GaaS server, waiting for it to start...",
                  end="", flush=True)
            o = server_process.stdout.readline()
            if "Starting GaaS..." in o :
                time.sleep(1)
                print("started.", flush=True)
            else:
                raise RuntimeError(f"error starting server: {o}")
        except:
            if server_process.poll() is None:
                server_process.terminate()
            raise

        yield

        print("\nTerminating server...", end="", flush=True)
        server_process.terminate()
        print("done.", flush=True)


@pytest.fixture(scope="function")
def client(server):
    from gaas_client import GaasClient, defaults

    client = GaasClient(defaults.host, defaults.port)
    # FIXME: this ensures a server that was running from a previous test is
    # empty. Consider a different way to test using a new server instance.
    for gid in client.get_graph_ids():
        client.delete_graph(gid)

    client.unload_graph_creation_extensions()

    yield client
    client.close()


@pytest.fixture(scope="function")
def client_with_csv_loaded(client):
    test_data = _data["karate"]
    client.load_csv_as_edge_data(test_data["csv_file_name"],
                                 dtypes=test_data["dtypes"],
                                 vertex_col_names=["0", "1"],
                                 type_name="")
    assert client.get_graph_ids() == [0]
    return (client, test_data)


###############################################################################
## tests

def test_get_num_edges_default_graph(client_with_csv_loaded):
    (client, test_data) = client_with_csv_loaded
    assert client.get_num_edges() == test_data["num_edges"]

def test_load_csv_as_edge_data_nondefault_graph(client):
    from gaas_client.exceptions import GaasError

    test_data = _data["karate"]

    with pytest.raises(GaasError):
        client.load_csv_as_edge_data(test_data["csv_file_name"],
                                     dtypes=test_data["dtypes"],
                                     vertex_col_names=["0", "1"],
                                     type_name="",
                                     graph_id=9999)

def test_get_num_edges_nondefault_graph(client_with_csv_loaded):
    from gaas_client.exceptions import GaasError

    (client, test_data) = client_with_csv_loaded
    with pytest.raises(GaasError):
        client.get_num_edges(9999)

    new_graph_id = client.create_graph()
    client.load_csv_as_edge_data(test_data["csv_file_name"],
                                 dtypes=test_data["dtypes"],
                                 vertex_col_names=["0", "1"],
                                 type_name="",
                                 graph_id=new_graph_id)

    assert client.get_num_edges() == test_data["num_edges"]
    assert client.get_num_edges(new_graph_id) == test_data["num_edges"]


def test_node2vec(client_with_csv_loaded):
    (client, test_data) = client_with_csv_loaded
    extracted_gid = client.extract_subgraph()
    start_vertices = 11
    max_depth = 2
    (vertex_paths, edge_weights, path_sizes) = \
        client.node2vec(start_vertices, max_depth, extracted_gid)
    # FIXME: consider a more thorough test
    assert isinstance(vertex_paths, list) and len(vertex_paths)
    assert isinstance(edge_weights, list) and len(edge_weights)
    assert isinstance(path_sizes, list) and len(path_sizes)


def test_extract_subgraph(client_with_csv_loaded):
    (client, test_data) = client_with_csv_loaded
    Gid = client.extract_subgraph(create_using=None,
                                  selection=None,
                                  edge_weight_property="2",
                                  default_edge_weight=None,
                                  allow_multi_edges=False)
    # FIXME: consider a more thorough test
    assert Gid in client.get_graph_ids()


def test_load_and_call_graph_creation_extension(client,
                                                graph_creation_extension):
    """
    Tests calling a user-defined server-side graph creation extension from the
    GaaS client.
    """
    # The graph_creation_extension returns the tmp dir created which contains
    # the extension
    extension_dir = graph_creation_extension

    num_files_loaded = client.load_graph_creation_extensions(extension_dir)
    assert num_files_loaded == 1

    new_graph_ID = client.call_graph_creation_extension(
        "my_graph_creation_function", "a", "b")

    assert new_graph_ID in client.get_graph_ids()

    # Inspect the PG and ensure it was created from my_graph_creation_function
    # FIXME: add client APIs to allow for a more thorough test of the graph
    assert client.get_num_edges(new_graph_ID) == 2
