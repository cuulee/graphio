import logging
from py2neo import Node, Relationship, Subgraph
from py2neo.ogm import GraphObject
from uuid import uuid4

from graphio.neo4j.queries import nodes_create_unwind, query_merge_nodes_unwind
from graphio.objects.helper import chunks
from graphio import defaults
from graphio.objects.relationshipset import RelationshipSet

log = logging.getLogger(__name__)


class NodeSet(GraphObject):
    """
    Container for a set of Nodes with the same labels and the same properties that define uniqueness.
    """

    def __init__(self, labels, merge_keys=None, batch_size=None):
        """

        :param labels: The labels for the nodes in this NodeSet.
        :type labels: list[str]
        :param merge_keys: The properties that define uniqueness of the nodes in this NodeSet.
        :type merge_keys: list[str]
        :param batch_size: Batch size for Neo4j operations.
        :type batch_size: int
        """
        self.labels = labels
        self.merge_keys = merge_keys

        self.combined = '_'.join(sorted(self.labels)) + '_' + '_'.join(sorted(self.merge_keys))
        self.uuid = str(uuid4())

        if batch_size:
            self.batch_size = batch_size
        else:
            self.batch_size = defaults.BATCHSIZE

        self.nodes = []

    def add_node(self, properties):
        """
        Create a node in this NodeSet. If a Node subclass is provided,
        the function create an instance of the subclass.

        :param properties: Node properties.
        :type properties: dict
        """
        n = Node(*self.labels, **properties)

        self.nodes.append(n)

    def add_nodes(self, list_of_properties):
        for properties in list_of_properties:
            self.add_node(properties)

    def to_dict(self):
        """
        Create dictionary defining each node.
        """
        for node in self.nodes:
            yield dict(node)

    def create(self, graph, batch_size=None):
        """
        Create all nodes from NodeSet.
        """
        log.debug('Create NodeSet')
        if not batch_size:
            batch_size = self.batch_size
        log.debug('Batch Size: {}'.format(batch_size))

        i = 1
        for batch in chunks(self.nodes, size=batch_size):
            batch = Subgraph(list(batch))
            log.debug('Batch {}'.format(i))

            graph.create(batch)
            i += 1

    def filter_nodes(self, filter_func):
        """
        Filter node properties with a filter function, remove nodes that do not match from main list.
        """
        filtered_nodes = []
        discarded_nodes = []
        for n in self.nodes:
            node_properties = dict(n)
            if filter_func(node_properties):
                filtered_nodes.append(n)
            else:
                discarded_nodes.append(n)

        self.nodes = filtered_nodes
        self.discarded_nodes = discarded_nodes

    def reduce_node_properties(self, *keep_props):
        filtered_nodes = []
        for n in self.nodes:
            new_props = {}
            for k, v in dict(n).items():
                if k in keep_props:
                    new_props[k] = v

            filtered_nodes.append(Node(*self.labels, **new_props))

        self.nodes = filtered_nodes

    def merge(self, graph, merge_properties, batch_size=None):
        """
        Merge nodes from NodeSet on merge properties.

        :param merge_properties: The merge properties.
        """
        log.debug('Merge NodeSet on {}'.format(merge_properties))

        if not batch_size:
            batch_size = self.batch_size

        log.debug('Batch Size: {}'.format(batch_size))

        query = query_merge_nodes_unwind(self.labels, merge_properties)
        log.debug(query)

        i = 1
        for batch in chunks(self.node_properties(), size=batch_size):
            batch = list(batch)
            log.debug('Batch {}'.format(i))
            log.debug(batch[0])
            graph.run(query, props=batch)
            i += 1

    def map_to_1(self, graph, target_labels, target_properties, rel_type=None):
        """
        Create relationships from all nodes in this NodeSet to 1 target node.

        :param graph: The py2neo Graph
        :param other_node: The target node.
        :param rel_type: Relationship Type
        """

        if not rel_type:
            rel_type = 'FROM_SET'

        rels = RelationshipSet(rel_type, self.labels, target_labels, self.merge_keys, target_properties)

        for node in self.nodes:
            # get properties for merge_keys
            node_properties = {}
            for k in self.merge_keys:
                node_properties[k] = node[k]

            rels.add_relationship(node_properties, target_properties, {})

        rels.create(graph)

    def node_properties(self):
        """
        Yield properties of the nodes in this set. Used for create function.
        """
        for n in self.nodes:
            yield dict(n)

    def all_properties_in_nodeset(self):
        """
        Return a set of all property keys in this NodeSet

        :return: A set of unique property keys of a NodeSet
        """
        all_props = set()

        # collect properties
        for props in self.node_properties():
            for k in props:
                all_props.add(k)

        return all_props
