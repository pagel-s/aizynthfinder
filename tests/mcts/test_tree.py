from aizynthfinder.search.mcts import MctsSearchTree


def test_select_leaf_root(setup_complete_mcts_tree):
    tree, nodes = setup_complete_mcts_tree
    nodes[0].is_expanded = False

    leaf = tree.select_leaf()

    assert leaf is nodes[0]


def test_select_leaf(setup_complete_mcts_tree):
    tree, nodes = setup_complete_mcts_tree

    leaf = tree.select_leaf()

    assert leaf is nodes[2]


def test_backpropagation(setup_complete_mcts_tree, mocker):
    tree, nodes = setup_complete_mcts_tree
    for node in nodes:
        node.backpropagate = mocker.MagicMock()
    score = tree.reward_scorer[tree.reward_scorer_name](nodes[2])

    tree.backpropagate(nodes[2])

    nodes[0].backpropagate.assert_called_once_with(nodes[1], score)
    nodes[1].backpropagate.assert_called_once_with(nodes[2], score)
    nodes[2].backpropagate.assert_not_called()


def test_route_to_node(setup_complete_mcts_tree):
    tree, nodes = setup_complete_mcts_tree

    actions, route_nodes = nodes[2].path_to()

    assert len(actions) == 2
    assert len(nodes) == 3
    assert nodes[0] == route_nodes[0]
    assert nodes[1] == route_nodes[1]
    assert nodes[2] == route_nodes[2]


def test_create_graph(setup_complete_mcts_tree):
    tree, nodes = setup_complete_mcts_tree

    graph = tree.graph()

    assert len(graph) == 3
    assert list(graph.successors(nodes[0])) == [nodes[1]]
    assert list(graph.successors(nodes[1])) == [nodes[2]]


def test_prune_tree_duplicate_state(setup_policies, default_config):
    root_smiles = "CCCO"
    expansions = {
        root_smiles: [
            {"smiles": "CCBr", "prior": 0.7},
            {"smiles": "CCCl", "prior": 0.5},
        ],
        "CCBr": {"smiles": "O", "prior": 1.0},
        "CCCl": {"smiles": "O", "prior": 1.0},
    }
    default_config.search.algorithm_config["tree_duplicate_pruning_start_transform"] = 0
    setup_policies(expansions, config=default_config)
    tree = MctsSearchTree(config=default_config, root_smiles=root_smiles)
    root = tree.root

    root.expand()
    first_child = root.promising_child()
    assert first_child is not None
    first_child.expand()
    assert first_child.promising_child() is not None

    second_child = root._select_child(1)
    assert second_child is not None
    second_child.expand()

    assert second_child.promising_child() is None
    assert second_child.children_view()["values"] == [-1000000.0]


def test_tree_duplicate_pruning_respects_start_transform(
    setup_policies, default_config
):
    root_smiles = "CCCO"
    expansions = {
        root_smiles: [
            {"smiles": "CCBr", "prior": 0.7},
            {"smiles": "CCCl", "prior": 0.5},
        ],
        "CCBr": {"smiles": "O", "prior": 1.0},
        "CCCl": {"smiles": "O", "prior": 1.0},
    }
    default_config.search.algorithm_config["tree_duplicate_pruning_start_transform"] = 5
    setup_policies(expansions, config=default_config)
    tree = MctsSearchTree(config=default_config, root_smiles=root_smiles)
    root = tree.root

    root.expand()
    first_child = root.promising_child()
    assert first_child is not None
    first_child.expand()
    assert first_child.promising_child() is not None

    second_child = root._select_child(1)
    assert second_child is not None
    second_child.expand()

    assert second_child.promising_child() is not None
