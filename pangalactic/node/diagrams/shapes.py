"""
Shapes and connectors for diagrams
"""
from collections import OrderedDict
from copy import deepcopy
# import functools
from textwrap import wrap

from PyQt5.QtCore import Qt, QLineF, QPointF, QRectF, QSizeF
from PyQt5.QtGui import (QColor, QFont, QPainterPath, QPen, QPolygonF,
                         QTextOption)
from PyQt5.QtWidgets import (QDialog, QGraphicsItem, QGraphicsLineItem,
                             QGraphicsTextItem, QMenu, QMessageBox, QStyle)

from louie import dispatcher

# pangalactic
from pangalactic.core             import state
from pangalactic.core.access      import get_perms
from pangalactic.core.parametrics import (data_elementz, get_dval,
                                          get_pval, parameterz)
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.utils.meta  import (get_acu_id, get_acu_name,
                                          get_flow_id, get_flow_name,
                                          get_next_port_seq, get_port_id,
                                          get_next_ref_des, 
                                          get_port_name)
from pangalactic.core.validation  import get_bom_oids
from pangalactic.node.dialogs     import (AssemblyNodeDialog,
                                          ConnectionsDialog,
                                          DirectionalityDialog,
                                          OptionNotification)
from pangalactic.node.filters     import FilterDialog
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
    ('thermal',            Qt.lightGray),
    ('gas',                Qt.black),
    ('unknown',            Qt.gray)
    ])
# Map of PortType.id to definitional parameter id:
PORT_TYPE_PARAMETERS = OrderedDict([
    ('electrical_power',   'V'),
    ('propulsion_power',   'P'),  # should be "Thrust"!
    ('electronic_control', ''),
    ('analog_data',        'R_D'),
    ('digital_data',       'R_D'),
    ('comm',               'f'),
    ('thermal',            'P'),
    ('gas',                'm'),
    ('unknown',            '')
    ])
PORT_TYPES = list(PORT_TYPE_COLORS.keys())


class Block(QGraphicsItem):
    """
    A Block represents a Product (which can be a Model of either an artifact or
    a natural phenomenon).  This is intended to be an abstract base class.

    NOTES:
        * if connectors are needed, implement them in a subclass
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 port_spacing=0):
        """
        Initialize Block.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Product):  object (Product instance) the block represents
            style (Qt.PenStyle):  style of block border
        """
        super().__init__()
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable)
        self.rect = QRectF(0, -POINT_SIZE, 20 * POINT_SIZE, 20 * POINT_SIZE)
        self.style = style or Qt.SolidLine
        # TODO:  notify the user if 'obj' is not a Product instance ... that
        # will cause errors
        self.__obj = obj
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

    @property
    def obj(self):
        return self.__obj

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        """
        Paint the item.
        """
        pen = QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def set_dashed_border(self):
        self.style = Qt.DashLine
        self.refresh()

    def set_solid_border(self):
        self.style = Qt.SolidLine
        self.refresh()

    def itemChange(self, change, value):
        return value

    # def contextMenuEvent(self, event):
        # # TODO, if we want generic "Block" menu ...
        # pass

    def setStyle(self, style):
        self.style = style
        # NOTE: update() schedules a repaint of the area covered by the block
        self.update()
        global Dirty
        Dirty = True

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
        port_order.sort(key=lambda x: x[0])
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
        # remove any existing port blocks and re-initialize port_blocks dict
        if self.port_blocks:
            for pb in self.port_blocks.values():
                self.scene().removeItem(pb)
        self.port_blocks = {}
        right = getattr(self, 'right_ports', True)
        # place initial port at 2 * port_spacing from top of block
        next_port_y = 2 * self.port_spacing
        for port in self.ordered_ports:
            # orb.log.debug('  - creating a PortBlock for {} ...'.format(
                                                                    # port.id))
            pb = PortBlock(self, port, right=right)
            if right:
                x = self.rect.width() - pb.rect.width()/2
            else:
                x = -(pb.rect.width()/2)
            pb.setPos(x, next_port_y)
            next_port_y += PORT_SIZE + self.port_spacing
            # populate `port_blocks` dict, used in restoring diagrams
            self.port_blocks[port.oid] = pb
            # orb.log.debug('    position: {!r}'.format(pb.pos()))
            # orb.log.debug('    scene coords: {!r}'.format(pb.scenePos()))
        # once all port blocks are created, resize if necessary to fit them
        comfy_height = self.childrenBoundingRect().height() + 50
        if comfy_height > self.rect.height():
            self.prepareGeometryChange()
            self.rect.setHeight(comfy_height)
            # NOTE: update() repaints the area covered by the block
            self.update()


class ObjectBlock(Block):
    """
    An ObjectBlock represents a "usage" (Acu or ProjectSystemUsage) of a
    product within an assembly or a project, which is represented by the
    SubjectBlock that contains the ObjectBlock.

    Attributes:
        has_sub_diagram (bool): flag indicating the block can be "drilled
            down" to reveal another (sub) diagram
        usage (Acu or ProjectSystemUsage):  usage the block represents
        obj (Product):  the 'component' attribute of the block's 'usage'
    """
    def __init__(self, position, scene=None, usage=None, style=None,
                 color=Qt.black, right_ports=False):
        """
        Initialize ObjectBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            usage (Acu or ProjectSystemUsage):  usage the block represents
            style (Qt.PenStyle):  style of block border
        """
        component = (getattr(usage, 'component', None) or
                     getattr(usage, 'system', None))
        super().__init__(position, scene=scene,
                                          obj=component, style=style)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable)
        self.setAcceptDrops(True)
        self.rect = QRectF(0, -POINT_SIZE, 20 * POINT_SIZE, 20 * POINT_SIZE)
        self.style = style or Qt.SolidLine
        self.color = color or Qt.black
        self.right_ports = right_ports
        self.usage = usage
        # self.connectors = []
        self.setPos(position)
        # scene.clearSelection()
        # self.setSelected(True)
        # self.setFocus()
        # ObjectBlocks get a higher z-value than SubjectBlocks
        # (so they can receive mouse events)
        z_value = 1.0
        self.setZValue(z_value)
        self.rebuild_port_blocks()
        # NOTE: update() repaints the area covered by the block
        self.update()
        dispatcher.connect(self.on_block_mod_signal, 'block mod')
        global Dirty
        Dirty = True

    @property
    def obj(self):
        return (getattr(self.usage, 'component', None) or
                getattr(self.usage, 'system', None))

    @property
    def has_sub_diagram(self):
        return bool(hasattr(self.obj, 'components')
                    and len(self.obj.components))

    def get_usage(self):
        return self.__usage

    def set_usage(self, link):
        if not isinstance(link,
            (orb.classes['Acu'], orb.classes['ProjectSystemUsage'])):
            msg = '"usage" must be either an Acu or a ProjectSystemUsage.'
            raise TypeError(msg)
        if isinstance(link, orb.classes['Acu']):
            obj = link.component
        else:
            obj = link.system
        hint = ''
        refdes = ''
        description = ''
        if isinstance(link, orb.classes['Acu']):
            pt = getattr(obj, 'product_type', None)
            if pt and pt.abbreviation:
                hint = pt.abbreviation
            else:
                hint = getattr(link.product_type_hint, 'abbreviation',
                               'Unspecified Type')
            refdes = link.reference_designator or ''
            if link.quantity and link.quantity > 1:
                refdes = '{} ({})'.format(refdes, link.quantity)
                hint = '[{}] ({})'.format(hint, link.quantity)
            else:
                hint = '[{}]'.format(hint)
        else:
            if link.system:
                hint = getattr(link.system.product_type, 'abbreviation',
                               'Unspecified Type')
            else:
                hint = 'Unknown Type'
            refdes = link.system_role or ''
        hint = hint or 'Unspecified Type'
        if getattr(self, 'name_label', None):
            try:
                self.name_label.prepareGeometryChange()
                self.scene().removeItem(self.name_label)
            except:
                # C/C++ object has already been deleted
                pass
        if getattr(self, 'description_label', None):
            try:
                self.description_label.prepareGeometryChange()
                self.scene().removeItem(self.description_label)
            except:
                # C/C++ object has already been deleted
                pass
        if len(refdes) < 20:
            description = refdes
        else:
            description = hint
        tbd = orb.get('pgefobjects:TBD')
        if obj is tbd:
            name = "TBD"
            version = ''
            self.style = Qt.DashLine
            self.color = Qt.lightGray
        else:
            name = (getattr(obj, 'name', None) or
                    getattr(obj, 'id', 'unknown'))
            version = getattr(obj, 'version', '')
            if version:
                name += '<br>v.' + version
            self.style = Qt.SolidLine
            self.color = Qt.black
        self.name_label = BlockLabel(name, self)
        self.description_label = TextLabel(description, self,
                                           color='darkMagenta')
        self.description_label.setPos(2.0 * POINT_SIZE,
                                      0.0 * POINT_SIZE)
        self.__usage = link
        # NOTE: update() repaints the area covered by the block
        self.update()

    def del_usage(self):
        pass

    usage = property(get_usage, set_usage, del_usage, 'usage property')

    def on_block_mod_signal(self, oid=None):
        """
        Handler for "block mod" signal.
        """
        try:
            if oid == self.obj.oid:
                orb.log.debug('* received "block mod" signal')
                # setting usage calls set_usage(), which recreates label
                self.usage = self.usage
                # update() repaints the area covered by the block
                self.update()
        except:
            # wrapped C/C++ object may have been deleted
            orb.log.debug('* received "block mod" signal but exception ...')

    # def something(self):
        # orb.log.info('* doing something ...')
        # pass

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        pen = QPen(self.style)
        color = self.color or Qt.black
        pen.setColor(color)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def itemChange(self, change, value):
        return value

    def setStyle(self, style):
        self.style = style
        # NOTE: update() repaints the area covered by the block
        self.update()
        global Dirty
        Dirty = True

    def contextMenuEvent(self, event):
        orb.log.debug("* ObjectBlock: context menu evt")
        self.scene().clearSelection()
        self.setSelected(True)
        menu = QMenu()
        perms = get_perms(self.usage)
        obj = None
        self.allocs = None
        if isinstance(self.usage, orb.classes['Acu']):
            obj = self.usage.component
            self.allocs = self.usage.allocated_requirements
        if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
            obj = self.usage.system
            self.allocs = self.usage.system_requirements
        orb.log.debug("  permissions on usage: {}".format(str(perms)))
        if getattr(obj, 'id', 'TBD') == 'TBD':
            if isinstance(self.usage, orb.classes['Acu']):
                # block is TBD and usage is Acu ...
                menu.addAction('Display allowed product type',
                               self.display_type_hint)
        else:
            # block is not TBD -- enable viewing of the object ...
            menu.addAction('View this object', self.display_object)
        if self.allocs:
            menu.addAction('Show allocated requirements', self.display_reqts)
        else:
            if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                txt = '[No requirements are allocated to this system]'
            elif isinstance(self.usage, orb.classes['Acu']):
                txt = '[No requirements are allocated to this component]'
            a = menu.addAction(txt, self.noop)
            a.setEnabled(False)
        # NOTE: get_all_usage_flows() will come up empty if the usage is a
        # ProjectSystemUsage instance, since flows are not allowed to have a
        # Project as their flow_context.
        flows = orb.get_all_usage_flows(self.usage)
        if flows:
            if 'modify' in perms:
                flows_txt = 'Select or delete connections'
            else:
                flows_txt = 'Display info about connections'
            menu.addAction(flows_txt, self.select_connections)
        else:
            # if usage is a PSU, don't even mention connections in the menu
            if not isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                txt = '[This component has no connections in this assembly]'
                flows_act = menu.addAction(txt, self.noop)
                flows_act.setEnabled(False)
        if 'modify' in perms:
            if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                mod_usage_txt = 'Modify system role in project'
            elif isinstance(self.usage, orb.classes['Acu']):
                mod_usage_txt = 'Modify quantity and/or reference designator'
            menu.addAction(mod_usage_txt, self.mod_usage)
            if isinstance(self.usage, orb.classes['Acu']):
                menu.addAction('Remove this component', self.del_component)
        if 'delete' in perms:
            if isinstance(self.usage, orb.classes['Acu']):
                menu.addAction('Remove this function',
                               self.del_position)
            if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
                menu.addAction('Remove this system', self.del_system)
        menu.exec_(event.screenPos())

    def select_connections(self):
        """
        Handler for menu items "Select or delete connections" and
        "Display info about connections" (the former if the user has
        delete permission).  Note that the diagram objects are RoutedConnector
        instances but their associated "models" in the database are Flow
        instances.
        """
        perms = get_perms(self.usage)
        # check for 'modify' permission; if found, offer "delete" option
        # if 'modify' in perms:
        dlg = ConnectionsDialog(self.scene(), self.usage,
                                parent=self.parentWidget())
        dlg.show()

    def display_type_hint(self):
        type_hint = getattr(self.usage.product_type_hint, 'name', '')
        dlg = OptionNotification('Allowed Product Type',
                             f'<font color="red"><b>{type_hint}</b></font>',
                             parent=self.parentWidget())
        dlg.show()

    def display_object(self):
        if isinstance(self.usage, orb.classes['Acu']):
            obj = self.usage.component
        if isinstance(self.usage, orb.classes['ProjectSystemUsage']):
            obj = self.usage.system
        dispatcher.send(signal='display object', obj=obj)

    def display_reqts(self):
        h = state.get('height') or 700
        w = 2 * (state.get('width') or 1000) // 3
        dlg = FilterDialog(self.allocs, label='Allocated Requirements',
                           height=h, width=w, parent=self.parentWidget())
        dlg.show()

    def del_position(self):
        """
        Remove a position (i.e. an Acu) from a assembly.  Prohibit removal if
        associated flows exist.
        """
        # NOTE: permissions are checked in the context menu that gives access
        # to this function
        orb.log.debug('* ObjectBlock: del_position() ...')
        # remove any associated Flows first!
        orb.log.debug('  - checking for flows ...')
        flows = orb.get_all_usage_flows(self.usage)
        if flows:
            message = 'Cannot delete: all connections must be deleted first.'
            popup = QMessageBox(QMessageBox.Warning,
                        "CAUTION: Connections", message,
                        QMessageBox.Ok, self.parentWidget())
            popup.show()
            return
        else:
            orb.log.debug('   no associated flows.')
        oid = self.usage.oid
        orb.delete([self.usage])
        dispatcher.send(signal='deleted object', oid=oid, cname='Acu')

    def del_system(self):
        """
        Remove a system (i.e. a ProjectSystemUsage) from a project.  (User
        permissions are checked before access is granted to this function.)
        """
        # NOTE: permissions are checked in the context menu that gives access
        # to this function
        oid = self.usage.oid
        orb.delete([self.usage])
        dispatcher.send(signal='deleted object', oid=oid,
                        cname='ProjectSystemUsage')

    def del_component(self):
        """
        Remove a component from a function, replacing it with the `TBD` object.
        (User permissions are checked before access is granted to this
        function.)
        """
        # NOTE: permissions are checked in the context menu that gives access
        # to this function
        orb.log.debug('* ObjectBlock: del_component() ...')
        # remove any Flows first!
        orb.log.debug('  - checking for flows ...')
        flows = orb.get_all_usage_flows(self.usage)
        if flows:
            message = 'Cannot delete: all connections must be deleted first.'
            popup = QMessageBox(QMessageBox.Warning,
                        "CAUTION: Connections", message,
                        QMessageBox.Ok, self.parentWidget())
            popup.show()
            return
        else:
            orb.log.debug('   no associated flows.')
        tbd = orb.get('pgefobjects:TBD')
        self.usage.component = tbd
        self.usage.quantity = 1
        self.usage.mod_datetime = dtstamp()
        self.usage.modifier = orb.get(state.get('local_user_oid'))
        orb.save([self.usage])
        dispatcher.send(signal='modified object', obj=self.usage)

    def mod_usage(self):
        """
        If usage is an Acu, edit the 'quantity' and 'reference_designator', or
        if a ProjectSystemUsage, the 'system_role'.
        """
        user = orb.get(state.get('local_user_oid'))
        NOW = dtstamp()
        assembly = None
        if isinstance(self.usage, orb.classes['Acu']):
            orb.log.debug('  editing assembly node ...')
            ref_des = self.usage.reference_designator
            quantity = self.usage.quantity
            system = False
            assembly = self.usage.assembly
        elif isinstance(self.usage, orb.classes['ProjectSystemUsage']):
            orb.log.debug('  editing project system node ...')
            ref_des = self.usage.system_role
            quantity = None
            system = True
        else:
            return
        dlg = AssemblyNodeDialog(ref_des, quantity, system=system)
        if dlg.exec_() == QDialog.Accepted:
            if isinstance(self.usage, orb.classes['Acu']):
                self.usage.reference_designator = dlg.ref_des
                self.usage.quantity = dlg.quantity
            else:
                self.usage.system_role = dlg.ref_des
            self.usage.mod_datetime = NOW
            self.usage.modifier = user
            orb.save([self.usage])
            dispatcher.send('modified object', obj=self.usage)
            # Acu modified -> assembly is modified
            if assembly:
                assembly.mod_datetime = NOW
                assembly.modifier = user
                orb.save([assembly])
                dispatcher.send('modified object', obj=assembly)

    def noop(self):
        pass

    def mouseDoubleClickEvent(self, event):
        QGraphicsItem.mouseDoubleClickEvent(self, event)
        self.scene().item_doubleclick(self)

    def mousePressEvent(self, event):
        if self.scene():
            self.scene().clearSelection()
        self.setSelected(True)
        self.color = Qt.blue
        QGraphicsItem.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        QGraphicsItem.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        # orb.log.debug("* ObjectBlock: mouseReleaseEvent()")
        # deselect so another object can be selected
        self.setSelected(False)
        self.color = Qt.black
        QGraphicsItem.mouseReleaseEvent(self, event)

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product"]

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle the drop event on ObjectBlock.  This includes the following
        possible cases:

            00: user permissions prohibit operation -> abort
            0: dropped item would cause a cycle -> abort
            1: dropped item is not a Product -> abort
               (note that a Model is a Product, so in theory Models can be
               assembled ...  but in the current implementation the only
               allowed mime type is for HardwareProduct ... in future, more
               mime types will be added)
            2: drop target is "TBD" -> replace with dropped object
        """
        orb.log.debug("* ObjectBlock: hm, something dropped on me ...")
        # only accept the drop if dropped item is a HardwareProduct and our
        # object is TBD
        drop_target = self.obj
        # TODO:  add more mime types so any kind of product can be used to
        # populate a TBD block, if the product_type_hint allows it
        if not 'modify' in get_perms(self.usage):
            # --------------------------------------------------------
            # 00: user permissions prohibit operation -> abort
            # --------------------------------------------------------
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
            event.ignore()
            return
        if (event.mimeData().hasFormat("application/x-pgef-hardware-product")
            and drop_target.oid == 'pgefobjects:TBD'):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, oid, _id, name, cname = data
            dropped_item = orb.get(oid)
            if dropped_item:
                if self.usage.assembly.oid == oid:
                    # --------------------------------------------------------
                    # 0: dropped item would cause a cycle -> abort
                    # --------------------------------------------------------
                    orb.log.debug(
                      '    invalid: dropped object same as target object.')
                    popup = QMessageBox(
                                QMessageBox.Critical,
                                "Assembly same as Component",
                                "A product cannot be a component of itself.",
                                QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                    return
                bom_oids = get_bom_oids(dropped_item)
                if self.usage.assembly.oid in bom_oids:
                    # --------------------------------------------------------
                    # 0: dropped item would cause a cycle -> abort
                    # --------------------------------------------------------
                    popup = QMessageBox(
                            QMessageBox.Critical,
                            "Prohibited Operation",
                            "Product cannot be used in its own assembly.",
                            QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                    return
                orb.log.info('  - dropped_item: "{}"'.format(name))
                # drop target is "TBD" product -> replace it with the dropped
                # item if it has the right product_type
                # use dropped item if its product_type is the same as
                # acu's "product_type_hint"
                ptname = getattr(dropped_item.product_type,
                                 'name', '')
                hint = ''
                usage = self.usage
                if getattr(usage, 'product_type_hint', None):
                    # NOTE: 'product_type_hint' is a ProductType
                    hint = getattr(usage.product_type_hint,
                                   'name', '')
                elif getattr(usage, 'system_role', None):
                    # NOTE: 'system_role' the *name* of a ProductType
                    hint = usage.system_role
                if hint and (ptname != hint or not ptname):
                    msg = "dropped product is not a valid type; nothing done."
                    orb.log.info("  - {}".format(msg))
                    QMessageBox.critical(
                                self.parentWidget(), "Product Type Check",
                                "The product you dropped is not a "
                                "{}.".format(hint or "[unspecified type]"),
                                QMessageBox.Cancel)
                    event.accept()
                    return
                else:
                    # remove any Flows first!
                    # [NOTE: TBD blocks cannot currently have flows but may in
                    # the future ...]
                    orb.log.debug('  - checking for flows ...')
                    flows = orb.get_all_usage_flows(self.usage)
                    if flows:
                        for flow in flows:
                            orb.log.debug('   id: {}, name: {} (oid {})'.format(
                                          flow.id, flow.name, flow.oid))
                            orb.db.delete(flow)
                            orb.log.debug('     ... deleted.')
                        orb.db.commit()
                    else:
                        orb.log.debug('   no associated flows.')
                    mod_objs = []
                    pt = dropped_item.product_type
                    if isinstance(usage, orb.classes['Acu']):
                        usage.component = dropped_item
                        usage.product_type_hint = pt
                        # Acu is modified -> assembly is modified
                        # mod_objs.append(usage.assembly)
                    elif isinstance(usage, orb.classes['ProjectSystemUsage']):
                        usage.system = dropped_item
                        usage.system_role = pt.name
                    mod_objs.append(usage)
                    for obj in mod_objs:
                        obj.mod_datetime = dtstamp()
                        obj.modifier = orb.get(state.get('local_user_oid'))
                    orb.save(mod_objs)
                    # NOTE:  setting 'usage' triggers name/desc label rewrites
                    self.usage = usage
                    event.accept()
                    orb.log.debug('   usage modified: {}'.format(
                                  self.usage.name))
                    for obj in mod_objs:
                        dispatcher.send('modified object', obj=obj)
                    ### NOTE: this message is not being used -- maybe uncomment
                    ### when/if I figure out what I had in mind for it :P
                    # dispatcher.send('product dropped on object block',
                                    # p=dropped_item)
            else:
                orb.log.info("  - dropped product not in db; nothing done.")
                event.accept()
        else:
            orb.log.info("  - dropped object was not a Product")
            orb.log.info("    or was not dropped on a TBD -- ignored!")
            event.ignore()


class SubjectBlock(Block):
    """
    A SubjectBlock represents the object that is the subject of an Internal
    Block Diagram (IBD).

    Attributes:
        obj (Identifiable):  object the block represents
    """
    def __init__(self, position, scene=None, obj=None, style=None,
                 width=1000, height=500, right_ports=True):
        """
        Initialize SubjectBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Identifiable):  object the block represents
            style (Qt.PenStyle):  style of block border
            width (int):  width of block
            height (int):  height of block
            right_ports (bool):  flag indicating whether to place ports on
                right (if True) or left
        """
        super().__init__(position, scene=scene, obj=obj, style=style)
        self.setFlags(QGraphicsItem.ItemIsFocusable)
        self.setAcceptDrops(True)
        # this apparently does work, but not what I wanted
        # self.setAcceptedMouseButtons(Qt.NoButton)
        self.position = position
        self.rect = QRectF(0, 0, width, height)
        self.style = style or Qt.SolidLine
        self.__obj = obj   # used by the 'obj' property of Block
        # SubjectBlock ports are always on the right side
        self.right_ports = True
        self.rebuild()
        # SubjectBlocks get a z-value of 0 (lower than ObjectBlocks, so
        # ObjectBlocks can receive mouse events)
        z_value = 0.0
        self.setZValue(z_value)
        dispatcher.connect(self.on_block_mod_signal, 'block mod')
        global Dirty
        Dirty = True

    def rebuild(self):
        name = getattr(self.obj, 'name', None) or self.obj.id
        version = getattr(self.obj, 'version', '')
        if version:
            name += ' v.' + version
        if hasattr(self.obj, 'product_type'):
            desc = getattr(self.obj.product_type, 'abbreviation',
                           'Unspecified Type')
        else:
            # for now, if it doesn't have a product_type, it's a project ...
            desc = 'Project'
        description = '[{}]'.format(desc)
        self.setPos(self.position)
        if hasattr(self, 'description_label'):
            self.description_label.setText(description)
        else:
            self.description_label = TextLabel(description, self,
                                               color='darkMagenta')
            self.description_label.setPos(2.0 * POINT_SIZE, 0.0 * POINT_SIZE)
        name_x = 20
        name_y = self.description_label.boundingRect().height() + 5
        if hasattr(self, 'name_label'):
            self.name_label.set_text(name)
        else:
            self.name_label = BlockLabel(name, self, centered=False, x=name_x,
                                         y=name_y)
        self.rebuild_port_blocks()
        # NOTE: update() repaints the area covered by the block
        self.update()

    def parentWidget(self):
        return self.scene().views()[0]

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget):
        """
        Reimplemented paint() to avoid green highlight (which indicates
        drill-down-able -- not applicable to a SubjectBlock).
        """
        pen = QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if option.state & QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRect(self.rect)

    def on_block_mod_signal(self, oid=None):
        """
        Handler for "block mod" signal.
        """
        try:
            if oid == self.obj.oid:
                orb.log.debug('* received "block mod" signal')
                # self.rebuild() calls update()
                self.rebuild()
        except:
            # wrapped C/C++ object may have been deleted
            orb.log.debug('* received "block mod" signal but exception ...')

    def mimeTypes(self):
        """
        Return a list of the accepted mime types (a list of strings).
        """
        return ["application/x-pgef-hardware-product",
                "application/x-pgef-product-type",
                "application/x-pgef-port-type",
                "application/x-pgef-port-template"]

    def dragEnterEvent(self, event):
        """
        Accept the drag enter event if it has an accepted mime type.
        """
        orb.log.debug('  - drag object mime types: {}'.format(
                      event.mimeData().formats()))
        if (event.mimeData().hasFormat(
                                "application/x-pgef-hardware-product")
            or event.mimeData().hasFormat(
                                "application/x-pgef-product-type")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-type")
            or event.mimeData().hasFormat(
                                "application/x-pgef-port-template")):
            # self.dragOver = True
            # NOTE: update() repaints the area covered by the block
            # self.update()
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Handle the drop event on SubjectBlock.  This includes the following
        possible cases:

            00: user permissions prohibit operation -> abort
            0: dropped item would cause a cycle -> abort
            1: drop target is "TBD" -> disallow (SubjectBlock cannot be TBD)
            2: dropped item is a Product and
               drop target is a Product -> add a new component position
               with the dropped item as the new component
            3: drop target is a Project ->
               if drop item is a Product *and* it is not already in use
               on the Project, use it to create a new ProjectSystemUsage
            4: dropped item is a PortType and
               drop target is an object that can have ports ->
               add a Port to the drop target
            5: dropped item is a PortTemplate and
               drop target is an object that can have ports ->
               add a Port to the drop target
            6: dropped item is a ProductType and
               drop target is a Product -> add an empty function
               ("bucket") -- actually, an Acu with TBD component and the
               dropped ProductType as its product_type_hint -- to the Product
        """
        orb.log.debug("* SubjectBlock: hm, something dropped on me ...")
        user = orb.get(state.get('local_user_oid'))
        drop_target = self.obj
        orb.log.debug('  - target name: {}'.format(drop_target.name))
        # 00: user permissions prohibit operation -> abort
        if not 'modify' in get_perms(drop_target):
            # --------------------------------------------------------
            # 00: user permissions prohibit operation -> abort
            # --------------------------------------------------------
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
            event.ignore()
            return
        elif event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, obj_oid, obj_id, obj_name, obj_cname = data
            orb.log.info("  - it is a {} ...".format(obj_cname))
            # check if target is same as dropped object
            if drop_target.oid == obj_oid:
                # ------------------------------------------------------------
                # 0: dropped item same as target, would cause a cycle -> abort
                # ------------------------------------------------------------
                orb.log.debug(
                  '    invalid: dropped object same as target object.')
                popup = QMessageBox(
                            QMessageBox.Critical,
                            "Assembly same as Component",
                            "A product cannot be a component of itself.",
                            QMessageBox.Ok, self.parentWidget())
                popup.show()
                event.ignore()
                return
            dropped_item = orb.get(obj_oid)
            if dropped_item:
                orb.log.info('  - dropped object name: "{}"'.format(obj_name))
                # orb.log.info(
                    # '    sending message "product dropped on subject block"')
                ### NOTE: this message is not being used -- maybe uncomment it
                ### when/if I figure out what I had in mind for it :P
                # dispatcher.send('product dropped on subject block',
                                # p=dropped_item)
            else:
                orb.log.info("  - dropped product oid not in db.")
                event.ignore()
            target_cname = drop_target.__class__.__name__
            if issubclass(orb.classes[target_cname],
                          orb.classes['Product']):
                orb.log.debug('    + target is a Product ...')
                bom_oids = get_bom_oids(dropped_item)
                if drop_target.oid in bom_oids:
                    # ---------------------------------------------------------
                    # 0: target is a component of dropped item (cycle) -> abort
                    # ---------------------------------------------------------
                    popup = QMessageBox(
                            QMessageBox.Critical,
                            "Prohibited Operation",
                            "Product cannot be used in its own assembly.",
                            QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                    return
                if drop_target.oid == 'pgefobjects:TBD':
                    # --------------------------------------------------------
                    # 1: drop target is "TBD" -> disallow (SubjectBlock cannot
                    #    be TBD)
                    # --------------------------------------------------------
                    popup = QMessageBox(
                            QMessageBox.Critical,
                            "Prohibited Operation",
                            "Subject Block cannot be TBD.",
                            QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                    return
                # --------------------------------------------------------
                # 2: dropped item is a Product and
                #    drop target is a Product -> add a new component
                #    position with the dropped item as the new component
                # --------------------------------------------------------
                # add new Acu
                orb.log.info('      accepted as component ...')
                # orb.log.debug('      creating Acu ...')
                # generate a new reference_designator
                ref_des = get_next_ref_des(drop_target, dropped_item)
                # NOTE: clone() adds create/mod_datetime & creator/modifier
                new_acu = clone('Acu',
                    id=get_acu_id(drop_target.id, ref_des),
                    name=get_acu_name(drop_target.name, ref_des),
                    assembly=drop_target,
                    component=dropped_item,
                    product_type_hint=dropped_item.product_type,
                    creator=user,
                    create_datetime=dtstamp(),
                    modifier=user,
                    mod_datetime=dtstamp(),
                    reference_designator=ref_des)
                # new Acu -> drop target is modified (any computed
                # parameters must be recomputed, etc.)
                drop_target.mod_datetime = dtstamp()
                drop_target.modifier = user
                orb.save([new_acu, drop_target])
                # orb.log.debug('      Acu created: {}'.format(
                              # new_acu.name))
                self.scene().create_block(ObjectBlock, usage=new_acu)
                dispatcher.send('new object', obj=new_acu)
                dispatcher.send('new diagram block', acu=new_acu)
                dispatcher.send('modified object', obj=drop_target)
            elif target_cname == 'Project':
                # ------------------------------------------------------------
                # 3: drop target is a Project ->
                #    if drop item is a Product *and* it is not already in use
                #    on the Project, use it to create a new ProjectSystemUsage
                # ------------------------------------------------------------
                log_txt = '+ target is a Project -- adding new system ...'
                orb.log.debug('    {}'.format(log_txt))
                psu = orb.search_exact(cname='ProjectSystemUsage',
                                       project=drop_target,
                                       system=dropped_item)
                if psu:
                    QMessageBox.warning(self.parentWidget(),
                                    'Already exists',
                                    'System "{0}" already exists on '
                                    'project {1}'.format(
                                    dropped_item.name, drop_target.id))
                    return
                psu_id = ('psu-' + dropped_item.id + '-' +
                          drop_target.id)
                psu_name = ('psu: ' + dropped_item.name +
                            ' (system used on) ' + drop_target.name)
                psu_role = getattr(dropped_item.product_type, 'name',
                                   'System')
                new_psu = clone('ProjectSystemUsage',
                                id=psu_id,
                                name=psu_name,
                                creator=user,
                                create_datetime=dtstamp(),
                                modifier=user,
                                mod_datetime=dtstamp(),
                                system_role=psu_role,
                                project=drop_target,
                                system=dropped_item)
                orb.save([new_psu])
                # NOTE:  addition of a ProjectSystemUsage does not imply
                # that the Project is "modified" (maybe it should??)
                # orb.log.debug('      ProjectSystemUsage created: %s'
                              # % psu_name)
                self.scene().create_block(ObjectBlock, usage=new_psu)
                dispatcher.send('new object', obj=new_psu)

        elif event.mimeData().hasFormat("application/x-pgef-port-type"):
            # ------------------------------------------------------------
            # 4: dropped item is a PortType and
            #    drop target is a Product instance ->
            #    add a Port to the drop target
            # ------------------------------------------------------------
            data = extract_mime_data(event, "application/x-pgef-port-type")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            port_type = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                orb.log.info("  - {} cannot have ports.".format(
                                                self.obj.__class__.__name__))
                msg = "Only models of physical objects and software\n"
                msg += "can have ports."
                popup = QMessageBox(
                        QMessageBox.Critical,
                        "Prohibited Operation", msg,
                        QMessageBox.Ok, self.parentWidget())
                popup.show()
                event.ignore()
                return
            elif port_type:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info('    creating Port ...')
                seq = get_next_port_seq(self.obj, port_type)
                port_id = get_port_id(port_type.id, seq)
                port_name = get_port_name(port_type.name, seq)
                new_port = clone('Port', id=port_id, name=port_name,
                                 abbreviation=port_name,
                                 type_of_port=port_type, of_product=self.obj)
                orb.db.commit()
                dispatcher.send('new object', obj=new_port)
                # new Port -> self.obj is modified (parameters may need to
                # be recomputed, etc.)
                self.obj.mod_datetime = dtstamp()
                self.obj.modifier = orb.get(state.get('local_user_oid'))
                orb.save([self.obj])
                dispatcher.send('modified object', obj=self.obj)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped port type oid not in db.")
                event.ignore()
        elif event.mimeData().hasFormat("application/x-pgef-port-template"):
            # ------------------------------------------------------------
            # 5: dropped item is a PortTemplate and
            #    drop target is an object that can have ports ->
            #    add a Port to the drop target
            # ------------------------------------------------------------
            data = extract_mime_data(event, "application/x-pgef-port-template")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            port_template = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                orb.log.info("  - {} cannot have ports.".format(
                                                self.obj.__class__.__name__))
                msg = "Only models of physical objects and software\n"
                msg += "can have ports."
                popup = QMessageBox(
                        QMessageBox.Critical,
                        "Prohibited Operation", msg,
                        QMessageBox.Ok, self.parentWidget())
                popup.show()
                event.ignore()
            elif port_template:
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info('    creating Port ...')
                port_type = port_template.type_of_port
                seq = get_next_port_seq(self.obj, port_type)
                port_id = get_port_id(port_type.id, seq)
                port_name = get_port_name(port_type.name, seq)
                port_desc = port_template.description
                new_port = clone('Port', id=port_id, name=port_name,
                                 abbreviation=port_name, description=port_desc,
                                 type_of_port=port_type, of_product=self.obj,
                                 creator=user,
                                 create_datetime=dtstamp(),
                                 modifier=user,
                                 mod_datetime=dtstamp())
                orb.db.commit()
                # if the port_template has parameters, add them to the new port
                if parameterz.get(port_template.oid):
                    new_parameters = deepcopy(parameterz[port_template.oid])
                    parameterz[new_port.oid] = new_parameters
                if data_elementz.get(port_template.oid):
                    new_data_els = deepcopy(data_elementz[port_template.oid])
                    data_elementz[new_port.oid] = new_data_els
                dispatcher.send('new object', obj=new_port)
                self.obj.mod_datetime = dtstamp()
                self.obj.modifier = orb.get(state.get('local_user_oid'))
                orb.save([self.obj])
                dispatcher.send('modified object', obj=self.obj)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped port template not in db.")
                event.ignore()
        elif event.mimeData().hasFormat("application/x-pgef-product-type"):
            # ------------------------------------------------------------
            # 6: dropped item is a ProductType and
            #    drop target is a Product -> add an empty function
            #    ("bucket") -- actually, an Acu with TBD component and the
            #    dropped ProductType as its product_type_hint -- to the Product
            # ------------------------------------------------------------
            data = extract_mime_data(event, "application/x-pgef-product-type")
            icon, oid, _id, name, cname = data
            orb.log.info("  - it is a {} ...".format(cname))
            product_type = orb.get(oid)
            if product_type and isinstance(self.obj, orb.classes['Product']):
                orb.log.info('  - orb found {} "{}"'.format(cname, name))
                orb.log.info('    creating an empty function ...')
                ref_des = get_next_ref_des(drop_target, None,
                                           product_type=product_type)
                # NOTE: clone() adds create/mod_datetime & creator/modifier
                tbd = orb.get('pgefobjects:TBD')
                new_acu = clone('Acu',
                    id=get_acu_id(drop_target.id, ref_des),
                    name=get_acu_name(drop_target.name, ref_des),
                    assembly=drop_target,
                    component=tbd,
                    product_type_hint=product_type,
                    creator=user,
                    create_datetime=dtstamp(),
                    modifier=user,
                    mod_datetime=dtstamp(),
                    reference_designator=ref_des)
                # new Acu -> drop target is modified (any computed
                # parameters must be recomputed, etc.)
                drop_target.mod_datetime = dtstamp()
                drop_target.modifier = user
                orb.save([new_acu, drop_target])
                # orb.log.debug('      Acu created: {}'.format(
                              # new_acu.name))
                self.scene().create_block(ObjectBlock, usage=new_acu)
                dispatcher.send('new object', obj=new_acu)
                dispatcher.send('modified object', obj=drop_target)
                dispatcher.send('new diagram block', acu=new_acu)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped product type oid not in db.")
                event.ignore()
        else:
            orb.log.info("  - dropped object is not an allowed type")
            orb.log.info("    to drop on a subject block.")


class PortBlock(QGraphicsItem):
    """
    A PortBlock is a small block shape on the edge of an ObjectBlock.  It
    represents an interface (Port) in the Object represented by the
    ObjectBlock.  A Port can be associated with a Flow (e.g. energy, electrons,
    water), which is represented by a RoutedConnector attached to the
    PortBlock.
    """
    def __init__(self, parent_block, port, style=None, right=False):
        """
        Initialize a PortBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            parent_block (Block):  Block on which the PortBlock is created
            port (Port):  Port instance represented by the PortBlock
            style (Qt.PenStyle):  style of block border
            right (bool):  flag telling the PortBlock which side of its parent
                block it is on (used for routing connectors)
        """
        super().__init__(parent=parent_block)
        self.setFlags(
                      # QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsFocusable)
        self.port = port
        self.setAcceptHoverEvents(True)
        self.setToolTip(self.tooltip_text)
        self.rect = QRectF(0, -POINT_SIZE, PORT_SIZE, PORT_SIZE)
        self.triangle = QPolygonF()
        self.right_port = right
        self.style = style or Qt.SolidLine
        self.parent_block = parent_block
        self.obj = parent_block.obj
        self.connectors = []
        self.setOpacity(1.0)
        # PortBlocks get a higher z-value than ObjectBlocks or SubjectBlocks
        # (so they get precedence for mouse events)
        z_value = 2.0
        self.setZValue(z_value)
        global Dirty
        Dirty = True

    @property
    def tooltip_text(self):
        port_type_id = getattr(self.port.type_of_port, 'id')
        port_pid = PORT_TYPE_PARAMETERS.get(port_type_id, '')
        port_parm = parameterz.get(self.port.oid, {}).get(port_pid)
        tooltip_text = self.port.abbreviation or self.port.name
        units = ''
        pval = ''
        if port_parm:
            units = port_parm.get('units')
            pval = get_pval(self.port.oid, port_pid, units=units)
        # only show pval if other than zero
        if port_type_id == 'digital_data' and self.port.description:
            if pval and units:
                tooltip_text = '\n'.join([tooltip_text, self.port.description,
                                          '[' + str(pval) + ' ' + units + ']'])
            else:
                tooltip_text = '\n'.join([tooltip_text, self.port.description])
        elif pval and units:
            tooltip_text += ' [' + str(pval) + ' ' + units + ']'
        return tooltip_text

    def parentWidget(self):
        return self.parent_block.parentWidget()

    def contextMenuEvent(self, event):
        if isinstance(self.parent_block, (SubjectBlock, ObjectBlock)):
            # NOTE: the permissions related to a Port are those of its
            # "of_product" object
            perms = get_perms(self.port)
            self.scene().clearSelection()
            # self.setSelected(True)
            menu = QMenu()
            menu.addAction('inspect port object', self.display_port)
            flows = orb.get_all_port_flows(self.port)
            if flows:
                # delete is only allowed if the associated Port object has no
                # associated Flows (in ANY context!)
                txt = '[port cannot be deleted -- has external connections]'
                a = menu.addAction(txt, self.noop)
                a.setEnabled(False)
            if 'modify' in perms:
                # allow setting of directionality -- set_directionality() will
                # check for consistency with any existing flows
                set_dir_action = menu.addAction('set directionality',
                                                self.set_directionality)
                if state.get('connected'):
                    set_dir_action.setEnabled(True)
                else:
                    set_dir_action.setEnabled(False)
            if 'delete' in perms and not flows:
                # delete is only allowed if the associated Port object has no
                # associated Flows (in ANY context!)
                del_act = menu.addAction('delete port', self.delete_local)
                if state.get('connected'):
                    del_act.setEnabled(True)
                else:
                    del_act.setEnabled(False)
            if self.connectors:
                # if the port has connectors/flows, check whether the user has
                # modify permission for the flows (which is determined from the
                # permissions for the associated "flow_context")
                flow_perms = get_perms(self.connectors[0].flow)
                if 'modify' in flow_perms and state.get('connected'):
                    menu.addAction(
                        "delete this port's connections within this assembly",
                        self.delete_all_flows_local)
            menu.exec_(event.screenPos())
        else:
            event.ignore()

    def noop(self):
        pass

    def set_directionality(self):
        # get directionalities of all ports connected to this one
        gazintas = orb.gazintas(self.port)
        gazoutas = orb.gazoutas(self.port)
        otherdirs = set([get_dval(port.oid, 'directionality')
                         for port in gazintas + gazoutas])
        otherdirs &= set(['input', 'output'])
        orb.log.debug(f'* set_directionality: not {otherdirs}.')
        dlg = DirectionalityDialog(self.port, otherdirs=otherdirs,
                                   parent=self.parentWidget())
        dlg.show()

    def delete_local(self):
        """
        Do a locally-originated deletion.
        """
        self.delete(remote=False)

    def delete(self, remote=False):
        """
        Delete this PortBlock and its Port object if it does not have any
        associated Flows.  User permissions are checked before access is
        provided to this function.

        Keyword Args:
            remote (bool):  if True, action originated remotely, so a local
                "deleted object" signal should NOT be dispatched.
        """
        if self.connectors:
            # if the port has connectors, warn the user and ignore
            message = 'Cannot delete: all connections must be deleted first.'
            popup = QMessageBox(QMessageBox.Warning,
                        "CAUTION: Connections", message,
                        QMessageBox.Ok, self.parentWidget())
            popup.show()
            return
        txt = 'This will delete the {} port'.format(self.port.name)
        txt += ' -- are you sure?'
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete Port?', txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            # the PortBlock must have a Port, but check just to be sure ... it
            # might have already been deleted if this was a remote action
            if getattr(self, 'port', None):
                obj = self.port.of_product
                port_oid = self.port.oid
                orb.delete([self.port])
                dispatcher.send('deleted object', oid=port_oid,
                                cname='Port', remote=remote)
                # if local action, dispatch 'modified object' signal
                if not remote:
                    # set modifier / mod_datetime on port's object
                    user = orb.get(state.get('local_user_oid'))
                    obj.modifier = user
                    obj.mod_datetime = dtstamp()
                    orb.save([obj])
                    dispatcher.send('modified object', obj=obj)
            # regenerate the diagram
            dispatcher.send('refresh diagram')

    def delete_all_flows_local(self):
        self.delete_all_flows(remote=False)

    def delete_all_flows(self, remote=False):
        """
        Delete all associated Flows and their RoutedConnector objects.

        Keyword Args:
            remote (bool):  if True, action originated remotely, so a local
                "deleted object" signal should NOT be dispatched.
        """
        txt = 'This will delete all connections (Flows) associated with the '
        txt += f' {self.port.name} port -- are you sure?'
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete Connections?',
                                  txt, QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            # delete connector(s) and their associated flows, if any ...
            for shape in self.scene().items():
                if (isinstance(shape, RoutedConnector) and
                    (shape.start_item is self or shape.end_item is self)):
                    flow_oid = shape.flow.oid
                    orb.delete([shape.flow])
                    dispatcher.send('deleted object', oid=flow_oid,
                                    cname='Flow', remote=remote)
                    shape.prepareGeometryChange()
                    self.scene().removeItem(shape)
            # regenerate the diagram
            dispatcher.send('refresh diagram')

    def display_port(self):
        dispatcher.send(signal='display object', obj=self.port)

    def boundingRect(self):
        return self.rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter, option, widget):
        pen = QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(1)
        if option.state & QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        # set the brush by PortType (port.type_of_port)
        port_type_id = getattr(self.port.type_of_port, 'id')
        # if port type is not found, set white as port color
        painter.setBrush(PORT_TYPE_COLORS.get(port_type_id, Qt.white))
        if not (get_dval(self.port.oid, 'directionality') in ['input',
                                                              'output']):
            # not input or output port -- bidirectional: draw a rectangle
            painter.drawRect(self.rect)
        else:
            if (((get_dval(self.port.oid, 'directionality') == 'input')
                  and self.right_port) or
                ((get_dval(self.port.oid, 'directionality') == 'output')
                  and not self.right_port)
                  ):
                # left-pointing triangle
                p1 = self.rect.topRight()
                p2 = self.rect.bottomRight()
                p3 = QPointF(self.rect.topLeft().x(),
                             (self.rect.topLeft().y() +
                              self.rect.bottomLeft().y())/2.0)
            else:
                # right-pointing triangle
                p1 = self.rect.topLeft()
                p2 = self.rect.bottomLeft()
                p3 = QPointF(self.rect.topRight().x(),
                             (self.rect.topRight().y() +
                              self.rect.bottomRight().y())/2.0)
            self.triangle.clear()
            for point in [p1, p2, p3]:
                self.triangle.append(point)
            painter.drawPolygon(self.triangle)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
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
            # this removes the connector from its scene and removes its
            # associated Flow object, etc.
            connector.delete()


class EntityBlock(Block):
    """
    A block that represents an Entity, similar to the entity in an
    Entity-Relationship (ER) diagram.
    """
    def __init__(self, position, scene=None, obj=None, style=None):
        """
        Initialize EntityBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            obj (Identifiable):  object the block represents
            style (Qt.PenStyle):  style of block border
        """
        super().__init__(position, scene=None, obj=obj, style=style)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable |
                      QGraphicsItem.ItemIsFocusable)
        self.rect = QRectF(0, -POINT_SIZE, 20 * POINT_SIZE, 20 * POINT_SIZE)
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
        self.name_label = BlockLabel(name, self)
        self.title_separator = QGraphicsLineItem(
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
        pen = QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if self.isUnderMouse() and self.has_sub_diagram:
            pen.setColor(Qt.green)
            pen.setWidth(6)
        elif option.state & QStyle.State_Selected:
            pen.setColor(Qt.blue)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect, 10, 10)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            for connector in self.connectors:
                connector.updatePosition()
        return value

    def contextMenuEvent(self, event):
        # TODO ...
        pass
        # wrapped = []
        # menu = QMenu()
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
        # NOTE: update() repaints the area covered by the block
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
            # this removes the connector from its scene
            connector.delete()

    def mouseDoubleClickEvent(self, event):
        self.scene().item_doubleclick(self)


def segment_bounding_rect(segment):
    extra = 20
    p1 = segment.p1()
    p2 = segment.p2()
    # orb.log.debug("  - (%f, %f) to (%f, %f)" % (
                  # p1.x(), p1.y(), p2.x(), p2.y()))
    # return QRectF(
            # p1,
            # QSizeF(p2.x() - p1.x(), p2.y() - p1.y())
                # ).normalized().adjusted(-extra, -extra, extra, extra)
    return QRectF(
            p1,
            QSizeF(p2.x() - p1.x() + 1, p2.y() - p1.y() + 1)
                ).normalized().adjusted(-extra, -extra, extra, extra)


class RoutedConnector(QGraphicsItem):
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

    def __init__(self, start_item, end_item, routing_channel, context=None,
                 arrow=False, pen_width=2):
        """
        Initialize RoutedConnector.

        Args:
            start_item (PortBlock):  start port of connection
            end_item (PortBlock):  end port of connection
            routing_channel (list):  the left and right x-coordinates within
                which all flows should be routed

        Keyword Args:
            context (ManagedObject):  object that is the subject of the diagram
            arrow (bool):  flag indicating whether connector gets an arrow
            pen_width (int):  width of pen
        """
        super().__init__()
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.segments = []
        self.routing_channel = routing_channel
        # default is Electrical Power (red)
        self.type_of_flow = getattr(start_item.port.type_of_port, 'id',
                                    'electrical_power')
        self.color = PORT_TYPE_COLORS[self.type_of_flow]
        self.pen_width = pen_width
        self.normal_pen_width = pen_width
        self.wide_pen_width = pen_width + 5
        # NOTE:  arrow is not being used, since we terminate at a port
        self.arrow = arrow
        if arrow:
            self.arrow_head = QPolygonF()
        # NOTE: about "color" (and "pen_width" is the same):
        # to change the color of a RoutedConnector to a custom color ...
        #    * conn.pen.setColor(some special color)
        # to set the color of a RoutedConnector back to its original color ...
        #    * conn.pen.setColor(conn.color)  -- i.e., use "self.color"
        self.pen = QPen(self.color, pen_width, Qt.SolidLine, Qt.RoundCap,
                        Qt.RoundJoin)
        self.start_item = start_item
        self.end_item = end_item
        self.context = context
        self.setAcceptHoverEvents(True)
        # 'paints' is for dev analysis -- number of calls to paint()
        # self.paints = 0
        self.flow = orb.select('Flow', start_port=start_item.port,
                               end_port=end_item.port, flow_context=context)
        if not self.flow:
            user = orb.get(state.get('local_user_oid'))
            self.flow = clone('Flow',
                id=get_flow_id(start_item.port.id, end_item.port.id),
                name=get_flow_name(start_item.port.name, end_item.port.name),
                start_port=start_item.port, end_port=end_item.port,
                flow_context=context, creator=user, create_datetime=dtstamp(),
                modifier=user, mod_datetime=dtstamp())
            orb.db.commit()
            # new Flow -> context object is modified
            context.mod_datetime = dtstamp()
            context.modifier = user
            orb.save([context])
            dispatcher.send('modified object', obj=context)
        # orb.log.debug("* RoutedConnector created:")
        # orb.log.debug("  - start port id: {}".format(self.start_item.port.id))
        # orb.log.debug("  - end port id: {}".format(self.end_item.port.id))
        # orb.log.debug("  - context id: {}".format(self.context.id))

    def contextMenuEvent(self, event):
        # check whether user has permission to modify the 'context' object --
        # if not, they don't get the option
        self.scene().clearSelection()
        self.setSelected(True)
        menu = QMenu()
        # perms on flow could be checked but does the same and this is quicker
        if 'modify' in get_perms(self.context):
            del_act = menu.addAction('delete connector', self.delete_local)
            if state.get('connected'):
                del_act.setEnabled(True)
            else:
                del_act.setEnabled(False)
            menu.exec_(event.screenPos())
        else:
            menu.addAction('user has no modify permissions', self.noop)
            menu.exec_(event.screenPos())

    def noop(self):
        pass

    def delete_local(self):
        """
        Do a locally-originated delete.
        """
        self.delete(remote=False)

    def delete(self, remote=False):
        txt = 'This will delete the {}'.format(self.flow.name)
        txt += ' -- are you sure?'
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete Connector?',
                                  txt, QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            orb.log.debug("* deleting RoutedConnector:")
            orb.log.debug("  - start id: {}".format(self.start_item.obj.id))
            orb.log.debug("  - end id: {}".format(self.end_item.obj.id))
            if getattr(self, 'flow', None):
                flow_oid = self.flow.oid
                orb.delete([self.flow])
                if not remote:
                    dispatcher.send('deleted object', oid=flow_oid,
                                    cname='Flow')
            self.start_item.remove_connector(self)
            self.end_item.remove_connector(self)
            self.prepareGeometryChange()
            self.scene().removeItem(self)
            # deleted Flow -> context object is modified
            self.context.mod_datetime = dtstamp()
            self.context.modifier = orb.get(state.get('local_user_oid'))
            orb.save([self.context])
            dispatcher.send('modified object', obj=self.context)

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
        return QRectF(p1, QSizeF(p2.x() - p1.x(), p2.y() - p1.y())
                      ).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        if self.segments:
            path = QPainterPath()
            for segment in self.segments:
                path.addRect(segment_bounding_rect(segment))
        else:
            path = super().shape()
        if getattr(self, 'arrow', None):
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
        painter.setPen(self.pen)
        # NOTE: for a line, "brush" is irrelevant; "pen" determines color etc.
        # if self.isUnderMouse():
            # painter.setBrush(Qt.darkGray)
            # self.pen.setWidth(6)
        # else:
        # painter.setBrush(self.color)
        # routing channel is used together with the port type and the
        # "SEPARATION" factor (spacing between flows) to calculate the
        # x-position of the vertical segment, vertical_x (formerly known as
        # seg1p2x)
        if self.routing_channel:
            rc_left_x, rc_right_x = self.routing_channel
        else:
            rc_left_x, rc_right_x = 300, 400
        vertical_x = ((rc_left_x + rc_right_x)/2  # center of channel (?)
                      + SEPARATION * PORT_TYPES.index(self.type_of_flow))
        if start_right and not end_right:
        # [1] from left (obj right port), to right (obj left port)
            # arrow should point right
            right_arrow = True
            start_x_pad = start_item.boundingRect().width()
            end_x_pad = PORT_SIZE/2
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
                # NOTE: for some reason, the y needs a shim
                seg1p1y = start_item.scenePos().y() + 3
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
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            # NOTE: for some reason, the y needs a shim
            seg2p2y = end_item.scenePos().y() + 3
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QPointF(seg3p2x, seg3p2y)
        elif not start_right and end_right:
        # [2] from right (obj left port), to left (obj right port)
            # arrow should point left
            right_arrow = False
            start_x_pad = PORT_SIZE/2
            end_x_pad = end_item.boundingRect().width() + PORT_SIZE/2
            x_pad = start_x_pad + end_x_pad
            total_x = (end_item.scenePos().x()
                       - start_item.scenePos().x()
                       + x_pad)
            if total_x < 0:
                # NOTE:  currently this is the only supported case for
                # right-to-left connection
                # (seg1 is always horizontal)
                seg1p1x = start_item.scenePos().x() + start_x_pad
                seg1p2x = vertical_x
                # NOTE: for some reason, the y needs a shim
                seg1p1y = start_item.scenePos().y() + 3
                seg3p2x = end_item.scenePos().x() + start_x_pad
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
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            # NOTE: for some reason, the y needs a shim
            seg2p2y = end_item.scenePos().y() + 3
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QPointF(seg3p2x, seg3p2y)
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
                seg1p1x = start_item.scenePos().x() + PORT_SIZE/2
                seg1p2x = seg1p1x - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_jog + x_delta
                seg3p2x = end_item.scenePos().x() + PORT_SIZE/2
            elif x_delta < 0:
                seg1p1x = start_item.scenePos().x()
                seg1p2x = seg1p1x + x_delta - x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x + x_jog
                seg3p2x = end_item.scenePos().x()
            else:      # x_delta == 0
                seg1p1x = start_item.scenePos().x() + PORT_SIZE/2
                seg1p2x = seg1p1x - x_jog
                # NOTE: for some reason, the y needs a shim
                seg1p1y = start_item.scenePos().y() + 3
                # seg3p2x = seg1p2x + x_jog
                seg3p2x = end_item.scenePos().x() + PORT_SIZE/2
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            # NOTE: for some reason, the y needs a shim
            seg2p2y = end_item.scenePos().y() + 3
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QPointF(seg3p2x, seg3p2y)
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
                seg1p1x = start_item.scenePos().x() + start_x_pad + PORT_SIZE/2
                seg1p2x = seg1p1x + x_jog
                # NOTE: for some reason, the y needs a shim
                seg1p1y = start_item.scenePos().y() + 3
                # seg3p2x = seg1p2x - x_jog - start_x_pad + end_x_pad
                seg3p2x = end_item.scenePos().x() + PORT_SIZE/2
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            # NOTE: for some reason, the y needs a shim
            seg2p2y = end_item.scenePos().y() + 3
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QPointF(seg3p2x, seg3p2y)
        # orb.log.debug(" - new seg1 from (%f, %f) to (%f, %f)" % (seg1p1x,
                                                                 # seg1p1y,
                                                                 # seg1p2x,
                                                                 # seg1p1y))
        seg1 = QLineF(seg1p1, seg1p2)
        seg2 = QLineF(seg2p1, seg2p2)
        seg3 = QLineF(seg3p1, seg3p2)
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
                arrow_p1 = seg3p2 + QPointF(- arrow_size / 1.7,
                                            arrow_size / 4.0)
                arrow_p2 = seg3p2 + QPointF(- arrow_size / 1.7,
                                            - arrow_size / 4.0)
            else:
                # cases [2] and [4]: left-pointing arrow
                arrow_p1 = seg3p2 + QPointF(arrow_size / 1.7,
                                            - arrow_size / 4.0)
                arrow_p2 = seg3p2 + QPointF(arrow_size / 1.7,
                                            arrow_size / 4.0)
            self.arrow_head.clear()
            for point in [seg3p2, arrow_p1, arrow_p2]:
                self.arrow_head.append(point)
            painter.drawPolygon(self.arrow_head)
        # if self.isSelected():
            # painter.setPen(QPen(self.color, 1, Qt.DashLine))
            # myLine = QLineF(seg1)
            # myLine.translate(0, 4.0)
            # painter.drawLine(myLine)
            # myLine.translate(0, -8.0)
            # painter.drawLine(myLine)

    # def hoverEnterEvent(self, event):
        # super().hoverEnterEvent(event)
        # orb.log.debug("RoutedConnector hover enter...")
        # self.pen_width = self.wide_pen_width
        # self.update()

    # def hoverLeaveEvent(self, event):
        # super().hoverLeaveEvent(event)
        # orb.log.debug("RoutedConnector hover leave ...")
        # self.pen_width = self.normal_pen_width
        # self.update()


class BlockLabel(QGraphicsTextItem):
    """
    Label for a block "name", which may contain spaces (and therefore may be
    wrapped).  It is not editable through the UI but can be programmatically
    changed using setHtml().

    Args:
        text (str):  text of label
        parent (QWidget): parent item

    Keyword Args:
        font (QFont):  style of font
        x (int):  x location in local coordinates
        y (int):  y location in local coordinates
        color (str):  color of font (see QTCOLORS)
    """
    def __init__(self, text, parent, font_name=None, point_size=None,
                 weight=None, color=None, centered=True, x=None, y=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.centered = centered
        self.text_option = QTextOption()
        self.text_option.setWrapMode(QTextOption.WordWrap)
        self.document().setDefaultTextOption(self.text_option)
        self.x = x or 0
        self.y = y or 0
        self.set_text(text, color=color, font_name=font_name,
                      point_size=point_size, weight=weight)

    def set_text(self, text, font_name=None, point_size=None,
                 weight=None, color=None):
        self.setHtml('<h2>{}</h2>'.format(text))
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        self.font_name = font_name or getattr(self, 'font_name', "Arial")
        self.point_size = point_size or getattr(self, 'point_size', POINT_SIZE)
        self.weight = weight or getattr(self, 'weight', 75)
        font = QFont(self.font_name, self.point_size, weight=self.weight)
        self.setFont(font)
        self.document().setDefaultTextOption(self.text_option)
        self.setParentItem(self.parent)
        self.adjustSize()
        self.setTextWidth(self.parent.boundingRect().width() - 50)
        if self.centered:
            w = self.boundingRect().width()
            x = self.parent.boundingRect().center().x() - w/2
            h = self.boundingRect().height()
            y = self.parent.boundingRect().center().y() - h/2
        else:
            x = self.x
            y = self.y
        self.setPos(x, y)


class TextLabel(QGraphicsTextItem):
    """
    Label for a blob of text, which may contain spaces (and therefore may be
    wrapped).

    Args:
        text (str):  text of label
        parent (QWidget): parent item

    Keyword Args:
        font (QFont):  style of font
        color (str):  color of font (see QTCOLORS)
    """
    # TODO:  add scrolling capability
    def __init__(self, text, parent, font=QFont("Arial", POINT_SIZE),
                 color=None):
        # if nowrap:
            # textw = text
        # else:
            # textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super().__init__(parent=parent)
        # if not nowrap:
        self.text_option = QTextOption()
        self.text_option.setWrapMode(QTextOption.WordWrap)
        self.document().setDefaultTextOption(self.text_option)
        self.setTextWidth(parent.boundingRect().width() - 50)
        self.setFont(font)
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        self.set_text(text)

    def set_text(self, text, font_name=None, point_size=None,
                 weight=None, color=None):
        self.setHtml('<h2>{}</h2>'.format(text))
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        self.font_name = font_name or getattr(self, 'font_name', "Arial")
        self.point_size = point_size or getattr(self, 'point_size', POINT_SIZE)
        self.weight = weight or getattr(self, 'weight', 75)
        font = QFont(self.font_name, self.point_size, weight=self.weight)
        self.setFont(font)
        self.document().setDefaultTextOption(self.text_option)

    def itemChange(self, change, variant):
        if change != QGraphicsItem.ItemSelectedChange:
            global Dirty
            Dirty = True
        return QGraphicsTextItem.itemChange(self, change, variant)


class TextItem(QGraphicsTextItem):
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
    """
    # TODO:  add scrolling capability
    def __init__(self, text, position, scene,
                 font=QFont("Arial", POINT_SIZE),
                 color=None):
        textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super().__init__(textw)
        self.setFlags(QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsMovable)
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
        if change != QGraphicsItem.ItemSelectedChange:
            global Dirty
            Dirty = True
        return QGraphicsTextItem.itemChange(self, change, variant)

