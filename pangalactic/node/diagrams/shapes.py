"""
Shapes and connectors for diagrams
"""
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from collections import OrderedDict
# import functools
from textwrap import wrap

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from louie import dispatcher

# pangalactic
from pangalactic.core.access      import get_perms
from pangalactic.core.parametrics import parameterz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.meta  import (get_flow_id, get_flow_name,
                                          get_next_port_seq, get_port_abbr,
                                          get_port_id, get_port_name)
from pangalactic.node.pgxnobject  import PgxnObject
from pangalactic.node.utils       import clone, extract_mime_data

# constants
POINT_SIZE = 10
SEPARATION = 20     # spacing factor between flows (connector lines)
PORT_SIZE = 3.0 * POINT_SIZE
QTCOLORS = ['white', 'black', 'red', 'darkRed', 'green', 'darkGreen', 'blue',
            'darkBlue', 'cyan', 'darkCyan', 'magenta', 'darkMagenta', 'yellow',
            'darkYellow', 'gray', 'darkGray', 'lightGray', 'transparent']
# -----------------------------------------------------
# Qt's predefined QColor objects:
# -----------------------------------------------------
# Qt::white         3 White (#ffffff)
# Qt::black         2 Black (#000000)
# Qt::red           7 Red (#ff0000)
# Qt::darkRed      13 Dark red (#800000)
# Qt::green         8 Green (#00ff00)
# Qt::darkGreen    14 Dark green (#008000)
# Qt::blue          9 Blue (#0000ff)
# Qt::darkBlue     15 Dark blue (#000080)
# Qt::cyan         10 Cyan (#00ffff)
# Qt::darkCyan     16 Dark cyan (#008080)
# Qt::magenta      11 Magenta (#ff00ff)
# Qt::darkMagenta  17 Dark magenta (#800080)
# Qt::yellow       12 Yellow (#ffff00)
# Qt::darkYellow   18 Dark yellow (#808000)
# Qt::gray          5 Gray (#a0a0a4)
# Qt::darkGray      4 Dark gray (#808080)
# Qt::lightGray     6 Light gray (#c0c0c0)
# Qt::transparent  19 a transparent black value (i.e., QColor(0, 0, 0, 0))
# Qt::color0        0 0 pixel value (for bitmaps)
# Qt::color1        1 1 pixel value (for bitmaps)
# orange (not Qt for that):  QColor(255, 140, 0)
# -----------------------------------------------------

# Map of PortType.id to color:
PORT_TYPE_COLORS = OrderedDict([
    ('electrical_power',   Qt.red),
    ('propulsion_power',   QColor(255, 140, 0)),  # orange
    ('electronic_control', QColor(165, 42, 42)),  # brown
    ('analog_data',        Qt.cyan),
    ('digital_data',       Qt.green),
    ('comm',               Qt.blue),
    ('thermal',            Qt.yellow),
    ('gas',                Qt.black),
    ('unknown',            Qt.gray)
    ])
PORT_TYPES = PORT_TYPE_COLORS.keys()


class Block(QtWidgets.QGraphicsItem):
    """
    A Block represents a Product (which can be a Model of either an artifact or
    a natural phenomenon).  This is intended to be an abstract base class.

    NOTES:
        * if connectors are needed, implement them in a subclass
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 editable=False, port_spacing=0):
        """
        Initialize Block.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Product):  object (Product instance) the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
        """
        super(Block, self).__init__()
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.rect = QtCore.QRectF(0, -POINT_SIZE, 20 * POINT_SIZE,
                                  20 * POINT_SIZE)
        self.style = style or Qt.SolidLine
        # TODO:  notify the user if 'obj' is not a Product instance ... that
        # will cause errors
        self.obj = obj
        self.port_blocks = {}
        self.port_spacing = port_spacing or POINT_SIZE
        self.setPos(position)
        if scene:
            scene.clearSelection()
            scene.addItem(self)
        self.setSelected(True)
        self.setFocus()
        global Dirty
        Dirty = True

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def itemChange(self, change, value):
        return value

    # def contextMenuEvent(self, event):
        # # TODO, if we want generic "Block" menu ...
        # pass

    def setStyle(self, style):
        self.style = style
        self.update()
        global Dirty
        Dirty = True

    def mouseDoubleClickEvent(self, event):
        self.scene().item_doubleclick(self)

    @property
    def ordered_ports(self):
        """
        Ports of the block's object sorted by (1) port type, (2) port id.
        (Note that port.id includes the order of creation for a given port_type
        within the context of the block.)
        """
        if not hasattr(self.obj, 'ports'):
            return []
        if not self.obj.ports:
            return []
        port_order = []
        for port in self.obj.ports:
            port_type = getattr(port.type_of_port, 'id', 'unknown')
            port_order.append(((PORT_TYPES.index(port_type), port.id), port))
        port_order.sort()
        return [ptuple[1] for ptuple in port_order]

    def rebuild_port_blocks(self):
        """
        [Re]create PortBlock items for any Port instances owned by the Block's
        object.  This command is run when the Block is first created and
        whenever Ports are added or removed from its object.
        """
        if not hasattr(self.obj, 'ports'):
            return
        if not self.obj.ports:
            return
        # remove any existing port blocks
        if self.port_blocks:
            for oid, pb in self.port_blocks.items():
                del self.port_blocks[oid]
                self.scene().removeItem(pb)
        right = getattr(self, 'right_ports', True)
        # place initial port at 2 * port_spacing from top of block
        next_port_y = 2 * self.port_spacing
        for port in self.ordered_ports:
            orb.log.debug('  - creating a PortBlock for {} ...'.format(
                                                                    port.id))
            pb = PortBlock(self, port, right=right)
            if right:
                x = self.rect.width() - pb.rect.width()/2
            else:
                x = -(pb.rect.width()/2)
            pb.setPos(x, next_port_y)
            next_port_y += PORT_SIZE + self.port_spacing
            # populate `port_blocks` dict, used in restoring diagrams
            self.port_blocks[port.oid] = pb
            orb.log.debug('    position: {!r}'.format(pb.pos()))
            orb.log.debug('    scene coords: {!r}'.format(pb.scenePos()))
        # once all port blocks are created, resize if necessary to fit them
        comfy_height = self.childrenBoundingRect().height() + 50
        if comfy_height > self.rect.height():
            self.prepareGeometryChange()
            self.rect.setHeight(comfy_height)
            self.update()


class ObjectBlock(Block):
    """
    An ObjectBlock represents an object.

    Attributes:
        has_sub_diagram (bool): flag indicating the block can be "drilled
            down" to reveal another (sub) diagram
        obj (Identifiable):  object the block represents
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 editable=False, right_ports=False):
        """
        Initialize ObjectBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Identifiable):  object the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
        """
        super(ObjectBlock, self).__init__(position, scene=scene, obj=obj,
                                          style=style, editable=editable)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setAcceptDrops(True)
        self.rect = QtCore.QRectF(0, -POINT_SIZE, 20 * POINT_SIZE,
                                  20 * POINT_SIZE)
        self.style = style or Qt.SolidLine
        self.obj = obj
        self.right_ports = right_ports
        self.has_sub_diagram = False
        if hasattr(obj, 'components') and len(obj.components):
            self.has_sub_diagram = True
        name = getattr(obj, 'name', None) or obj.id
        version = getattr(obj, 'version', '')
        if version:
            name += '<br>v.' + version
        description = '[{}]'.format(
                            getattr(obj.product_type, 'name', 'Product'))
        # self.connectors = []
        self.setPos(position)
        self.name_label = NameLabel(name, self)
        self.description_label = TextLabel(description, self,
                                           color='darkMagenta')
        self.description_label.setPos(2.0 * POINT_SIZE, 0.0 * POINT_SIZE)
        scene.clearSelection()
        self.setSelected(True)
        self.setFocus()
        self.rebuild_port_blocks()
        self.update()
        global Dirty
        Dirty = True

    # def contextMenuEvent(self, event):
        # self.scene().clearSelection()
        # self.setSelected(True)
        # menu = QtWidgets.QMenu()
        # menu.addAction('do something blockish', self.something)
        # menu.exec_(event.screenPos())

    # def something(self):
        # pass

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def itemChange(self, change, value):
        return value

    def setStyle(self, style):
        self.style = style
        self.update()
        global Dirty
        Dirty = True

    def mouseDoubleClickEvent(self, event):
        self.scene().item_doubleclick(self)

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product"]
                # "application/x-pgef-port-type",
                # "application/x-pgef-port-template"]

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            # or event.mimeData().hasFormat(
                                # "application/x-pgef-port-type")
            # or event.mimeData().hasFormat(
                                # "application/x-pgef-port-template")):
            # self.dragOver = True
            # self.update()
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        orb.log.debug("* ObjectBlock: something dropped on me ...")
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            data = extract_mime_data(event, 
                                     "application/x-pgef-hardware-product")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            product = orb.get(oid)
            if product:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info(
                    '    sending message "product dropped on object block"')
                dispatcher.send('product dropped on object block', p=product)
            else:
                orb.log.info("  - dropped product oid not in db.")
                event.ignore()
        else:
            orb.log.info("  - dropped object is not an allowed type")
            orb.log.info("    to drop on object block.")


class SubjectBlock(Block):
    """
    A SubjectBlock represents the object that is the subject of an Internal
    Block Diagram (IBD).

    Attributes:
        obj (Identifiable):  object the block represents
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 editable=False, width=1000, height=500, right_ports=True):
        """
        Initialize SubjectBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Identifiable):  object the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
            width (int):  width of block
            height (int):  height of block
            right_ports (bool):  flag indicating whether to place ports on
                right (if True) or left
        """
        super(SubjectBlock, self).__init__(position, scene=scene, obj=obj,
                                          style=style, editable=editable)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setAcceptDrops(True)
        self.rect = QtCore.QRectF(0, 0, width, height)
        self.style = style or Qt.SolidLine
        self.obj = obj
        self.right_ports = right_ports
        name = getattr(obj, 'name', None) or obj.id
        version = getattr(obj, 'version', '')
        if version:
            name += ' v.' + version
        if hasattr(obj, 'product_type'):
            desc = getattr(obj.product_type, 'name', 'Product')
        else:
            # for now, if it doesn't have a product_type, it's a project ...
            desc = 'Project'
        description = '[{}]'.format(desc)
        # self.connectors = []
        self.setPos(position)
        self.name_label = NameLabel(name, self, x=20, y=20)
        self.description_label = TextLabel(description, self,
                                           color='darkMagenta')
        self.description_label.setPos(2.0 * POINT_SIZE, 0.0 * POINT_SIZE)
        self.rebuild_port_blocks()
        # make sure the SubjectBlock has the lowest z-value
        z_value = 0.0
        overlap_items = self.collidingItems()
        if overlap_items:
            for item in overlap_items:
                if (item.zValue() >= z_value and isinstance(item, Block)):
                    z_value = item.zValue() - 0.1
        self.setZValue(z_value)
        self.update()
        global Dirty
        Dirty = True

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        """
        Reimplemented paint() to avoid green highlight (which indicates
        drill-down-able -- not applicable to a SubjectBlock).
        """
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product",
                "application/x-pgef-port-type",
                "application/x-pgef-port-template"]

    def dragEnterEvent(self, event):
        if (event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-type")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-template")):
            # self.dragOver = True
            # self.update()
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        orb.log.debug("* SubjectBlock: something dropped on me ...")
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            data = extract_mime_data(event, 
                                     "application/x-pgef-hardware-product")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            product = orb.get(oid)
            if product:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info(
                    '    sending message "product dropped on subject block"')
                dispatcher.send('product dropped on subject block', p=product)
            else:
                orb.log.info("  - dropped product oid not in db.")
                event.ignore()
        elif event.mimeData().hasFormat("application/x-pgef-port-type"):
            data = extract_mime_data(event, "application/x-pgef-port-type")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            port_type = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                orb.log.info("  - {} cannot have ports.".format(
                                                self.obj.__class__.__name__))
                event.ignore()
            elif port_type:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info('    creating Port ...')
                seq = get_next_port_seq(self.obj, port_type)
                port_id = get_port_id(self.obj.id, port_type.id, seq)
                port_name = get_port_name(self.obj.name, port_type.name, seq)
                port_abbr = get_port_abbr(port_type.name, seq)
                new_port = clone('Port', id=port_id, name=port_name,
                                 abbreviation=port_abbr,
                                 type_of_port=port_type, of_product=self.obj)
                orb.db.commit()
                dispatcher.send('new object', obj=new_port)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped port type oid not in db.")
                event.ignore()
        elif event.mimeData().hasFormat("application/x-pgef-port-template"):
            data = extract_mime_data(event, "application/x-pgef-port-template")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            port_template = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                orb.log.info("  - {} cannot have ports.".format(
                                                self.obj.__class__.__name__))
                event.ignore()
            elif port_template:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info('    creating Port ...')
                port_type = port_template.type_of_port
                seq = get_next_port_seq(self.obj, port_type)
                port_id = get_port_id(self.obj.id, port_type.id, seq)
                port_name = get_port_name(self.obj.name, port_type.name, seq)
                port_abbr = get_port_abbr(port_type.name, seq)
                port_desc = port_template.description
                new_port = clone('Port', id=port_id, name=port_name,
                                 abbreviation=port_abbr, description=port_desc,
                                 type_of_port=port_type, of_product=self.obj)
                orb.db.commit()
                # if the port_template has parameters, add them to the new port
                if parameterz.get(port_template.oid):
                    new_parameters = parameterz[port_template.oid].copy()
                    parameterz[new_port.oid] = new_parameters
                dispatcher.send('new object', obj=new_port)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped port template oid not in db.")
                event.ignore()
        else:
            orb.log.info("  - dropped object is not an allowed type")
            orb.log.info("    to drop on object block.")


class PortBlock(QtWidgets.QGraphicsItem):
    """
    A PortBlock is a small block shape on the edge of an ObjectBlock.  It
    represents an interface (Port) in the Object represented by the
    ObjectBlock.  A Port can be associated with a Flow (e.g. energy, electrons,
    water), which is represented by a RoutedConnector attached to the
    PortBlock.
    """
    def __init__(self, parent_block, port, style=None, editable=False,
                 right=False):
        """
        Initialize a PortBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            parent_block (Block):  Block on which the PortBlock is created
            port (Port):  Port instance represented by the PortBlock
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
            right (bool):  flag telling the PortBlock which side of its parent
                block it is on (used for routing connectors)
        """
        super(PortBlock, self).__init__(parent=parent_block)
        self.setFlags(
                      # QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setAcceptHoverEvents(True)
        tooltip_text = port.abbreviation or port.name
        self.setToolTip(tooltip_text)
        self.rect = QtCore.QRectF(0, -POINT_SIZE, PORT_SIZE, PORT_SIZE)
        self.right_port = right
        self.style = style or Qt.SolidLine
        self.parent_block = parent_block
        self.obj = parent_block.obj
        self.port = port
        self.connectors = []
        self.setOpacity(1.0)
        global Dirty
        Dirty = True

    def parentWidget(self):
        return self.parent_block

    def contextMenuEvent(self, event):
        if isinstance(self.parent_block, SubjectBlock):
            perms = get_perms(self.port)
            self.scene().clearSelection()
            # self.setSelected(True)
            menu = QtWidgets.QMenu()
            menu.addAction('inspect port object', self.open_pxo)
            if 'delete' in perms:
                menu.addAction('delete port', self.delete)
            menu.exec_(event.screenPos())
        else:
            event.ignore()

    def delete(self):
        txt = 'This will delete the {}'.format(self.port.name)
        txt += ' and any associated Flow(s) -- are you sure?'
        confirm_dlg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question,
                                            'Delete Port?', txt,
                                            QtWidgets.QMessageBox.Yes |
                                            QtWidgets.QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QtWidgets.QMessageBox.Yes:
            # delete connector(s) and their associated flows, if any ...
            for shape in self.scene().items():
                if (isinstance(shape, RoutedConnector) and
                    (shape.start_item is self or shape.end_item is self)):
                    orb.delete([shape.flow])
                    self.scene().removeItem(shape)
            # the PortBlock must have a Port, but check just to be sure ...
            if getattr(self, 'port', None):
                orb.delete([self.port])
            # finally, delete the PortBlock itself ...
            parent_block = self.parent_block
            self.scene().removeItem(self)
            parent_block.rebuild_port_blocks()

    def open_pxo(self):
        pxo = PgxnObject(self.port)
        pxo.show()

    def boundingRect(self):
        return self.rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter, option, widget):
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(1)
        if option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        # set the brush by PortType (port.type_of_port)
        port_type_id = getattr(self.port.type_of_port, 'id')
        # if port type is not found, set white as port color
        painter.setBrush(PORT_TYPE_COLORS.get(port_type_id, Qt.white))
        painter.drawRect(self.rect)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            for connector in self.connectors:
                connector.updatePosition()
        return value

    def add_connector(self, connector):
        self.connectors.append(connector)

    def remove_connector(self, connector):
        try:
            self.connectors.remove(connector)
        except ValueError:
            pass

    def remove_connectors(self):
        for connector in self.connectors[:]:
            connector.start_item.remove_connector(connector)
            connector.end_item.remove_connector(connector)
            self.scene().removeItem(connector)


class EntityBlock(Block):
    """
    A block that represents an Entity, similar to the entity in an
    Entity-Relationship (ER) diagram.
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 editable=False):
        """
        Initialize EntityBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Identifiable):  object the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
        """
        super(EntityBlock, self).__init__(position, scene=None, obj=obj,
                                          style=style, editable=editable)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.rect = QtCore.QRectF(0, -POINT_SIZE, 20 * POINT_SIZE,
                                  20 * POINT_SIZE)
        self.style = style or Qt.SolidLine
        self.obj = obj
        self.has_sub_diagram = False
        if hasattr(obj, 'components') and len(obj.components):
            self.has_sub_diagram = True
        name = getattr(obj, 'id', 'id')
        version = getattr(obj, 'version', '')
        if version:
            name += ' v.' + version
        description = getattr(obj, 'name', '[text]')
        self.connectors = []
        self.setPos(position)
        self.name_label = NameLabel(name, self, editable=editable)
        self.title_separator = QtWidgets.QGraphicsLineItem(
                                        0.0, 2.0 * POINT_SIZE,
                                        20.0 * POINT_SIZE, 2.0 * POINT_SIZE,
                                        parent=self)
        self.description_label = TextLabel(description, self)
        self.description_label.setPos(0.0 * POINT_SIZE, 3.0 * POINT_SIZE)
        scene.clearSelection()
        self.setSelected(True)
        self.setFocus()
        global Dirty
        Dirty = True

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        pen = QtGui.QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect, 10, 10)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            for connector in self.connectors:
                connector.updatePosition()
        return value

    def contextMenuEvent(self, event):
        # TODO ...
        pass
        # wrapped = []
        # menu = QtWidgets.QMenu()
        # for text, param in (
                # ("&Solid", Qt.SolidLine),
                # ("&Dashed", Qt.DashLine),
                # ("D&otted", Qt.DotLine),
                # ("D&ashDotted", Qt.DashDotLine),
                # ("DashDo&tDotted", Qt.DashDotDotLine)):
            # wrapper = functools.partial(self.setStyle, param)
            # wrapped.append(wrapper)
            # menu.addAction(text, wrapper)
        # menu.exec_(event.screenPos())

    def setStyle(self, style):
        self.style = style
        self.update()
        global Dirty
        Dirty = True

    def add_connector(self, connector):
        self.connectors.append(connector)

    def remove_connector(self, connector):
        try:
            self.connectors.remove(connector)
        except ValueError:
            pass

    def remove_connectors(self):
        for connector in self.connectors[:]:
            connector.start_item.remove_connector(connector)
            connector.end_item.remove_connector(connector)
            self.scene().removeItem(connector)

    def mouseDoubleClickEvent(self, event):
        self.scene().item_doubleclick(self)


def segment_bounding_rect(segment):
    extra = 20
    p1 = segment.p1()
    p2 = segment.p2()
    # orb.log.debug("  - (%f, %f) to (%f, %f)" % (
                  # p1.x(), p1.y(), p2.x(), p2.y()))
    # return QtCore.QRectF(
            # p1,
            # QtCore.QSizeF(p2.x() - p1.x(), p2.y() - p1.y())
                # ).normalized().adjusted(-extra, -extra, extra, extra)
    return QtCore.QRectF(
            p1,
            QtCore.QSizeF(p2.x() - p1.x() + 1, p2.y() - p1.y() + 1)
                ).normalized().adjusted(-extra, -extra, extra, extra)


class RoutedConnector(QtWidgets.QGraphicsItem):
    """
    This is intended to be a connecting line composed of vertical and/or
    horizontal segments, routed so as to avoid other lines and diagram shapes
    """
    # NOTE:  currently only supports connectors between PortBlocks;
    #        to support other block types, may need refactoring into a base
    #        "RoutedConnector" class with subclasses (RoutedPortConnector,
    #        etc.)
    # -----------------------------------------------------
    # TODO:
    # [1] allow for text labels on connectors
    # [2] multiple connectors and spacing layout
    # [3] options for horizontal or vertical layout
    # ===============================================
    # Proposed colors for Ports / connectors:
    # * green ......... digital data
    # * purple/cyan ... analog sensor data
    # * red ........... electrical power
    # * yellow ........ thermal (e.g. heat pipes?)
    # * lt. grey ...... "mechanical" (is that some kind of linkage?)
    # * dk. grey ...... "environmental" energy flows of various types
    # * blue dashed ... EM waves (comm. signals)
    # * brown ......... actuator signal (e.g. launch dock actuator drive)
    # * black ......... gas lines (e.g. N2 or O2)

    def __init__(self, start_item, end_item, context=None, arrow=False,
                 pen_width=2):
        """
        Initialize RoutedConnector.

        Args:
            start_item (PortBlock):  start port of connection
            end_item (PortBlock):  end port of connection

        Keyword Args:
            context (ManagedObject):  object that is the subject of the diagram
            arrow (bool):  flag indicating whether connector gets an arrow
            pen_width (int):  width of pen
        """
        super(RoutedConnector, self).__init__()
        self.segments = []
        # default is Electrical Power (red)
        self.type_of_flow = getattr(start_item.port.type_of_port, 'id',
                                    'electrical_power')
        self.color = PORT_TYPE_COLORS[self.type_of_flow]
        self.pen = QtGui.QPen(self.color, pen_width, QtCore.Qt.SolidLine,
                              QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        self.start_item = start_item
        self.end_item = end_item
        self.context = context
        self.setAcceptHoverEvents(True)
        self.arrow = arrow
        self.pen_width = pen_width
        self.normal_pen_width = pen_width
        self.wide_pen_width = pen_width + 5
        if arrow:
            self.arrow_head = QtGui.QPolygonF()
        # 'paints' is for dev analysis -- number of calls to paint()
        # self.paints = 0
        flows = orb.search_exact(start_port=start_item.port,
                                 end_port=end_item.port)
        if flows:
            self.flow = flows[0]  # *should* only be one ...
        else:
            self.flow = clone('Flow',
                id=get_flow_id(start_item.port.id, end_item.port.id),
                name=get_flow_name(start_item.port.name, end_item.port.name),
                start_port=start_item.port, end_port=end_item.port,
                flow_context=context)
            orb.db.commit()
        orb.log.debug("* RoutedConnector created:")
        orb.log.debug("  - start port id: {}".format(self.start_item.port.id))
        orb.log.debug("  - end port id: {}".format(self.end_item.port.id))
        orb.log.debug("  - context id: {}".format(self.context.id))

    def contextMenuEvent(self, event):
        self.scene().clearSelection()
        self.setSelected(True)
        menu = QtWidgets.QMenu()
        menu.addAction('delete connector', self.delete)
        menu.exec_(event.screenPos())

    def delete(self):
        txt = 'This will delete the {}'.format(self.flow.name)
        txt += ' -- are you sure?'
        confirm_dlg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question,
                                            'Delete Connector?', txt,
                                            QtWidgets.QMessageBox.Yes |
                                            QtWidgets.QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QtWidgets.QMessageBox.Yes:
            orb.log.debug("* deleting RoutedConnector:")
            orb.log.debug("  - start id: {}".format(self.start_item.obj.id))
            orb.log.debug("  - end id: {}".format(self.end_item.obj.id))
            if getattr(self, 'flow', None):
                orb.delete([self.flow])
            self.start_item.remove_connector(self)
            self.end_item.remove_connector(self)
            self.scene().removeItem(self)

    def set_color(self, color):
        self._color = color
        for s in self.segments:
            s.color = color

    def get_color(self):
        return self._color

    def del_color(self):
        pass

    color = property(get_color, set_color, del_color, 'color property')

    def set_pen(self, pen):
        self._pen = pen
        for s in self.segments:
            s.set_pen(pen)

    def get_pen(self):
        return self._pen

    def del_pen(self):
        pass

    pen = property(get_pen, set_pen, del_pen, 'pen property')

    def p1(self):
        if self.segments:
            p1 = self.segments[0].p1()
        else:
            p1 = self.mapFromItem(self.start_item, 0, 0)
        return p1

    def p2(self):
        # TODO:  when all segments are present, uncomment
        # if self.segments:
            # p2 = self.segments[-1].p2()
        # else:
            # p2 = self.mapFromItem(self.end_item, 0, 0)
        p2 = self.mapFromItem(self.end_item, 0, 0)
        return p2

    def boundingRect(self):
        # orb.log.debug("RoutedConnector.boundingRect ...")
        # extra = (self.pen.width() + 20) / 2.0
        extra = (self.pen.width() + 20)
        p1 = self.p1()
        p2 = self.p2()
        # orb.log.debug("  - (%f, %f) to (%f, %f)" % (
                      # p1.x(), p1.y(), p2.x(), p2.y()))
        return QtCore.QRectF(
                p1,
                QtCore.QSizeF(p2.x() - p1.x(), p2.y() - p1.y())
                    ).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        if self.segments:
            path = QtGui.QPainterPath()
            for segment in self.segments:
                path.addRect(segment_bounding_rect(segment))
        else:
            path = super(RoutedConnector, self).shape()
        if self.arrow:
            path.addPolygon(self.arrow_head)
        return path

    def updatePosition(self):
        # orb.log.debug("RoutedConnector.updatePosition ...")
        self.start = self.mapFromItem(self.start_item, 0, 0)
        self.end = self.mapFromItem(self.end_item, 0, 0)

    def paint(self, painter, option, widget=None):
        # self.paints += 1
        # orb.log.debug("RoutedConnector.paint %i ..." % self.paints)
        # TODO: compute how many segments (horizontal/vertical) to use
        if (self.start_item.collidesWithItem(self.end_item)):
            return
        start_item = self.start_item
        end_item = self.end_item
        start_right = start_item.right_port
        end_right = end_item.right_port
        # if one of the items is a SubjectBlock port, reverse the corresponding
        # start_right|end_right, since it will connect on its "inner" side
        if isinstance(start_item.parent_block, SubjectBlock):
            start_right = not start_right
        elif isinstance(end_item.parent_block, SubjectBlock):
            end_right = not end_right
        arrow_size = 20.0
        self.pen.setWidth(self.pen_width)
        painter.setPen(self.pen)
        # if self.isUnderMouse():
            # painter.setBrush(Qt.darkGray)
            # self.pen.setWidth(6)
        # else:
        painter.setBrush(self.color)
        # get the routing channel and use it together with the port type and
        # the "SEPARATION" factor (spacing between flows) to calculate the
        # x-position of the vertical segment, vertical_x (formerly known as
        # seg1p2x)
        rc_left_x, rc_right_x = self.scene().get_routing_channel()
        vertical_x = ((rc_left_x + rc_right_x)/2  # center of channel (?)
                      + SEPARATION * PORT_TYPES.index(self.type_of_flow))
        if start_right and not end_right:
        # [1] from left (obj right port), to right (obj left port)
            # arrow should point right
            right_arrow = True
            start_x_pad = start_item.boundingRect().width()
            end_x_pad = 0.0
            x_pad = start_x_pad + end_x_pad
            total_x = (end_item.scenePos().x()
                       - start_item.scenePos().x()
                       - x_pad)
            if total_x > 0:
                # NOTE:  currently this is the only supported case for
                # left-to-right connection
                # (seg1 is always horizontal)
                seg1p1x = start_item.scenePos().x() + start_x_pad
                # seg1p2x = seg1p1x + total_x/2.0
                seg1p2x = vertical_x
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + total_x/2.0
                seg3p2x = end_item.scenePos().x()
            elif total_x <= 0:   # FIXME!
                # NOTE: THIS IS INCORRECT ... need special case:
                # seg1 vertical, seg2 horizontal, seg3 vertical
                seg1p1x = start_item.scenePos().x() - start_x_pad
                # seg1p2x = seg1p1x + total_x/2.0
                seg1p2x = vertical_x
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + total_x/2.0
                seg3p2x = end_item.scenePos().x()
            else:               # FIXME!
                # NOTE: THIS IS INCORRECT ... need special case:
                # (= 0 => vertical segment only)
                seg1p1x = seg1p2x = start_item.scenePos().x()
                seg1p2x = seg1p1x + total_x/2.0
                seg1p1y = start_item.scenePos().y()
                seg3p2x = seg1p2x + total_x/2.0
            seg1p1 = QtCore.QPointF(seg1p1x, seg1p1y)
            seg1p2 = QtCore.QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QtCore.QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QtCore.QPointF(seg3p2x, seg3p2y)
        elif not start_right and end_right:
        # [2] from right (obj left port), to left (obj right port)
            # arrow should point left
            right_arrow = False
            start_x_pad = 0.0
            # end_x_pad = 0.0
            end_x_pad = end_item.boundingRect().width()
            x_pad = start_x_pad + end_x_pad
            total_x = (end_item.scenePos().x()
                       - start_item.scenePos().x()
                       + x_pad)
            if total_x < 0:
                # NOTE:  currently this is the only supported case for
                # right-to-left connection
                # (seg1 is always horizontal)
                seg1p1x = start_item.scenePos().x()
                # add end_x_pad (width of end port) here
                # seg1p2x = seg1p1x + total_x/2.0
                seg1p2x = vertical_x
                seg1p1y = start_item.scenePos().y()
                # don't need end_x_pad here -- already in seg1p2x
                # seg3p2x = seg1p2x + total_x/2.0
                seg3p2x = end_item.scenePos().x()
            elif total_x >= 0:   # FIXME!
                # THIS IS INCORRECT ... need special case:
                # seg1 vertical, seg2 horizontal, seg3 vertical
                seg1p1x = start_item.scenePos().x() - start_x_pad
                # seg1p2x = seg1p1x + total_x/2.0
                seg1p2x = vertical_x
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + total_x/2.0
                seg3p2x = end_item.scenePos().x()
            else:               # FIXME!
                # THIS IS INCORRECT ... need special case:
                # (= 0 => vertical segment only)
                seg1p1x = seg1p2x = start_item.scenePos().x()
                seg1p2x = seg1p1x + total_x/2.0
                seg1p1y = start_item.scenePos().y()
                seg3p2x = seg1p2x + total_x/2.0
            seg1p1 = QtCore.QPointF(seg1p1x, seg1p1y)
            seg1p2 = QtCore.QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QtCore.QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QtCore.QPointF(seg3p2x, seg3p2y)
        elif not start_right and not end_right:
        # [3] from start_item left port to end_item left port
            # arrow should point right
            right_arrow = True
            start_x_pad = start_item.boundingRect().width()
            end_x_pad = end_item.boundingRect().width()
            x_pad = start_x_pad + end_x_pad
            x_delta = end_item.scenePos().x() - start_item.scenePos().x()
            shim = 4.0 * POINT_SIZE
            x_jog = shim + (SEPARATION * PORT_TYPES.index(self.type_of_flow))
            if x_delta > 0:
                # seg1 is horizontal
                seg1p1x = start_item.scenePos().x()
                seg1p2x = seg1p1x - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_jog + x_delta
                seg3p2x = end_item.scenePos().x()
            elif x_delta < 0:
                seg1p1x = start_item.scenePos().x()
                seg1p2x = seg1p1x + x_delta - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_jog
                seg3p2x = end_item.scenePos().x()
            else:      # x_delta == 0
                seg1p1x = start_item.scenePos().x()
                seg1p2x = seg1p1x - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_jog
                seg3p2x = end_item.scenePos().x()
            seg1p1 = QtCore.QPointF(seg1p1x, seg1p1y)
            seg1p2 = QtCore.QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QtCore.QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QtCore.QPointF(seg3p2x, seg3p2y)
        elif start_right and end_right:
        # [4] from start_item right port to end_item right port
            # arrow should point left
            right_arrow = False
            start_x_pad = start_item.boundingRect().width()
            end_x_pad = end_item.boundingRect().width()
            x_delta = end_item.scenePos().x() - start_item.scenePos().x()
            shim = 4.0 * POINT_SIZE
            x_jog = shim + (SEPARATION * PORT_TYPES.index(self.type_of_flow))
            if x_delta > 0:
                # seg1 is horizontal
                seg1p1x = start_item.scenePos().x() + start_x_pad
                seg1p2x = seg1p1x + x_jog + x_delta
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x - x_jog - start_x_pad + end_x_pad
                seg3p2x = end_item.scenePos().x()
            elif x_delta < 0:
                seg1p1x = start_item.scenePos().x() + start_x_pad
                seg1p2x = seg1p1x - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_delta + x_jog - start_x_pad + end_x_pad
                seg3p2x = end_item.scenePos().x()
            else:      # x_delta == 0
                seg1p1x = start_item.scenePos().x() + start_x_pad
                seg1p2x = seg1p1x + x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x - x_jog - start_x_pad + end_x_pad
                seg3p2x = end_item.scenePos().x()
            seg1p1 = QtCore.QPointF(seg1p1x, seg1p1y)
            seg1p2 = QtCore.QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QtCore.QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QtCore.QPointF(seg3p2x, seg3p2y)
            seg1p1 = QtCore.QPointF(seg1p1x, seg1p1y)
            seg1p2 = QtCore.QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QtCore.QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QtCore.QPointF(seg3p2x, seg3p2y)
        # orb.log.debug(" - new seg1 from (%f, %f) to (%f, %f)" % (seg1p1x,
                                                                 # seg1p1y,
                                                                 # seg1p2x,
                                                                 # seg1p1y))
        seg1 = QtCore.QLineF(seg1p1, seg1p2)
        seg2 = QtCore.QLineF(seg2p1, seg2p2)
        seg3 = QtCore.QLineF(seg3p1, seg3p2)
        self.segments.append(seg1)
        self.segments.append(seg2)
        self.segments.append(seg3)
        painter.drawLine(seg1)
        painter.drawLine(seg2)
        painter.drawLine(seg3)
        # arrow head stuff
        arrow_size = 40.0
        if self.arrow:
            if right_arrow:
                # cases [1] and [3]: right-pointing arrow
                arrow_p1 = seg3p2 + QtCore.QPointF(- arrow_size / 1.7,
                                                   arrow_size / 4.0)
                arrow_p2 = seg3p2 + QtCore.QPointF(- arrow_size / 1.7,
                                                   - arrow_size / 4.0)
            else:
                # cases [2] and [4]: left-pointing arrow
                arrow_p1 = seg3p2 + QtCore.QPointF(arrow_size / 1.7,
                                                   - arrow_size / 4.0)
                arrow_p2 = seg3p2 + QtCore.QPointF(arrow_size / 1.7,
                                                   arrow_size / 4.0)
            self.arrow_head.clear()
            for point in [seg3p2, arrow_p1, arrow_p2]:
                self.arrow_head.append(point)
            painter.drawPolygon(self.arrow_head)
        # if self.isSelected():
            # painter.setPen(QtGui.QPen(self.color, 1, QtCore.Qt.DashLine))
            # myLine = QtCore.QLineF(seg1)
            # myLine.translate(0, 4.0)
            # painter.drawLine(myLine)
            # myLine.translate(0, -8.0)
            # painter.drawLine(myLine)

    # def hoverEnterEvent(self, event):
        # super(RoutedConnector, self).hoverEnterEvent(event)
        # orb.log.debug("RoutedConnector hover enter...")
        # self.pen_width = self.wide_pen_width
        # self.update()

    # def hoverLeaveEvent(self, event):
        # super(RoutedConnector, self).hoverLeaveEvent(event)
        # orb.log.debug("RoutedConnector hover leave ...")
        # self.pen_width = self.normal_pen_width
        # self.update()


class NameLabel(QtWidgets.QGraphicsTextItem):
    """
    Label for a "name", which may contain spaces (and therefore may be
    wrapped).  It is not editable through the UI but can be programmatically
    changed (using setHtml()).

    Args:
        text (str):  text of label
        parent (QWidget): parent item

    Keyword Args:
        font (QFont):  style of font
        x (int):  x location in local coordinates
        y (int):  y location in local coordinates
        color (str):  color of font (see QTCOLORS)
        editable (bool):  whether the text should be editable
    """
    def __init__(self, text, parent,
                 font=QtGui.QFont("Arial", POINT_SIZE, weight=75),
                 x=None, y=None, color=None):
        super(NameLabel, self).__init__(parent=parent)
        text_option = QtGui.QTextOption()
        text_option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.document().setDefaultTextOption(text_option)
        self.setHtml('<h2>{}</h2>'.format(text))
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        self.setTextWidth(parent.boundingRect().width() - 50)
        # self.adjustSize()
        if x is None:
            w = self.boundingRect().width()
            x = parent.boundingRect().center().x() - w/2
        if y is None:
            h = self.boundingRect().height()
            y = parent.boundingRect().center().y() - h/2
        self.setPos(x, y)
        self.setFont(font)


class TextLabel(QtWidgets.QGraphicsTextItem):
    """
    Label for a blob of text, which may contain spaces (and therefore may be
    wrapped).

    Args:
        text (str):  text of label
        parent (QWidget): parent item

    Keyword Args:
        font (QFont):  style of font
        color (str):  color of font (see QTCOLORS)
        editable (bool):  whether the text should be editable
    """
    # TODO:  add scrolling capability
    def __init__(self, text, parent, font=QtGui.QFont("Arial", POINT_SIZE),
                 color=None, editable=False):
        textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super(TextLabel, self).__init__(textw, parent=parent)
        text_option = QtGui.QTextOption()
        text_option.setWrapMode(QtGui.QTextOption.WordWrap)
        self.document().setDefaultTextOption(text_option)
        self.setTextWidth(parent.boundingRect().width() - 50)
        self.setFont(font)
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        if editable:
            self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable)

    def itemChange(self, change, variant):
        if change != QtWidgets.QGraphicsItem.ItemSelectedChange:
            global Dirty
            Dirty = True
        return QtWidgets.QGraphicsTextItem.itemChange(self, change, variant)

    def mouseDoubleClickEvent(self, event):
        dialog = TextItemDlg(self, self.parentWidget())
        dialog.exec_()


class TextItem(QtWidgets.QGraphicsTextItem):
    """
    Widget to contain a blob of text, which may contain spaces (and therefore
    may be wrapped).

    Args:
        text (str):  text of label
        position (QPointF): position in the scene
        scene (QGraphicsScene):  the containing scene

    Keyword Args:
        font (QFont):  style of font
        color (str):  color of font (see QTCOLORS)
        editable (bool):  whether the text should be editable
    """
    # TODO:  add scrolling capability
    def __init__(self, text, position, scene,
                 font=QtGui.QFont("Arial", POINT_SIZE),
                 color=None):
        textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super(TextItem, self).__init__(textw)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsMovable)
        self.setFont(font)
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        self.setPos(position)
        scene.clearSelection()
        scene.addItem(self)
        self.setSelected(True)
        global Dirty
        Dirty = True

    def parentWidget(self):
        return self.scene().views()[0]

    def itemChange(self, change, variant):
        if change != QtWidgets.QGraphicsItem.ItemSelectedChange:
            global Dirty
            Dirty = True
        return QtWidgets.QGraphicsTextItem.itemChange(self, change, variant)

    def mouseDoubleClickEvent(self, event):
        dialog = TextItemDlg(self, self.parentWidget())
        dialog.exec_()


class TextItemDlg(QtWidgets.QDialog):

    def __init__(self, item=None, position=None, scene=None, parent=None):
        super(QtWidgets.QDialog, self).__init__(parent)
        self.item = item
        self.position = position
        self.scene = scene
        self.create_widgets()
        self.layout_widgets()
        self.create_connections()
        self.setWindowTitle("Page Designer - {0} Text Item".format(
                "Add" if self.item is None else "Edit"))
        self.updateUi()

    def create_widgets(self):
        self.editor = QtWidgets.QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setTabChangesFocus(True)
        self.editorLabel = QtWidgets.QLabel("&Text:")
        self.editorLabel.setBuddy(self.editor)
        self.fontComboBox = QtWidgets.QFontComboBox()
        self.fontComboBox.setCurrentFont(QtGui.QFont("Arial", POINT_SIZE))
        self.fontLabel = QtWidgets.QLabel("&Font:")
        self.fontLabel.setBuddy(self.fontComboBox)
        self.fontSpinBox = QtWidgets.QSpinBox()
        self.fontSpinBox.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.fontSpinBox.setRange(6, 280)
        self.fontSpinBox.setValue(POINT_SIZE)
        self.fontSizeLabel = QtWidgets.QLabel("&Size:")
        self.fontSizeLabel.setBuddy(self.fontSpinBox)
        self.buttonBox = QtWidgets.QDialogButtonBox(
                                          QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)

        if self.item is not None:
            self.editor.setPlainText(self.item.toPlainText())
            self.fontComboBox.setCurrentFont(self.item.font())
            self.fontSpinBox.setValue(self.item.font().pointSize())

    def layout_widgets(self):
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.editorLabel, 0, 0)
        layout.addWidget(self.editor, 1, 0, 1, 6)
        layout.addWidget(self.fontLabel, 2, 0)
        layout.addWidget(self.fontComboBox, 2, 1, 1, 2)
        layout.addWidget(self.fontSizeLabel, 2, 3)
        layout.addWidget(self.fontSpinBox, 2, 4, 1, 2)
        layout.addWidget(self.buttonBox, 3, 0, 1, 6)
        self.setLayout(layout)

    def create_connections(self):
        self.fontComboBox.currentFontChanged.connect(self.updateUi)
        self.fontSpinBox.valueChanged.connect(self.updateUi)
        self.editor.textChanged.connect(self.updateUi)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def updateUi(self):
        font = self.fontComboBox.currentFont()
        font.setPointSize(self.fontSpinBox.value())
        self.editor.document().setDefaultFont(font)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(
                              bool(self.editor.toPlainText()))

    def accept(self):
        if self.item is None:
            self.item = TextItem("", self.position, self.scene)
        font = self.fontComboBox.currentFont()
        font.setPointSize(self.fontSpinBox.value())
        self.item.setFont(font)
        textw = '\n'.join(wrap(self.editor.toPlainText(), width=25,
                                 break_long_words=False))
        self.item.setPlainText(textw)
        self.item.update()
        global Dirty
        Dirty = True
        QtWidgets.QDialog.accept(self)


