"""
Shapes and connectors for diagrams
"""
from collections import OrderedDict
# import functools
from textwrap import wrap

from PyQt5.QtCore import Qt, QLineF, QPointF, QRectF, QSizeF
from PyQt5.QtGui import (QColor, QFont, QPainterPath, QPen, QPolygonF,
                         QTextOption)
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFontComboBox,
                             QGraphicsItem, QGraphicsLineItem,
                             QGraphicsTextItem, QGridLayout, QLabel, QMenu,
                             QMessageBox, QSpinBox, QStyle, QTextEdit)

from louie import dispatcher

# pangalactic
from pangalactic.core             import state
from pangalactic.core.access      import get_perms
from pangalactic.core.parametrics import parameterz
from pangalactic.core.uberorb     import orb
from pangalactic.core.utils.datetimes import dtstamp
from pangalactic.core.utils.meta  import (get_acu_id, get_acu_name,
                                          get_flow_id, get_flow_name,
                                          get_next_port_seq, get_port_id,
                                          get_next_ref_des, 
                                          get_port_name)
from pangalactic.core.validation  import get_bom_oids
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
    ('thermal',            Qt.lightGray),
    ('gas',                Qt.black),
    ('unknown',            Qt.gray)
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
                 color=Qt.black, editable=False, right_ports=False):
        """
        Initialize ObjectBlock.

        Args:
            position (QPointF):  where to put upper left corner of block
            scene (QGraphicsScene):  scene in which to create block

        Keyword Args:
            usage (Acu or ProjectSystemUsage):  usage the block represents
            style (Qt.PenStyle):  style of block border
            editable (bool):  flag indicating whether block properties can be
                edited in place
        """
        component = (getattr(usage, 'component', None) or
                     getattr(usage, 'system', None))
        super(ObjectBlock, self).__init__(position, scene=scene,
                                          obj=component, style=style,
                                          editable=editable)
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
        self.update()
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
        obj = (getattr(link, 'component', None) or
               getattr(link, 'system', None))
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
            if link.quantity:
                refdes = '{} ({})'.format(refdes, link.quantity)
                hint = '[{}] ({})'.format(hint, link.quantity)
            else:
                hint = '[{}]'.format(hint)
        else:
            hint = getattr(link.system.product_type, 'abbreviation',
                           'Unspecified Type')
            refdes = link.system_role or ''
        hint = hint or 'Unspecified Type'
        if getattr(self, 'name_label', None):
            self.name_label.prepareGeometryChange()
            self.scene().removeItem(self.name_label)
        if getattr(self, 'description_label', None):
            self.description_label.prepareGeometryChange()
            self.scene().removeItem(self.description_label)
        if len(refdes) < 20:
            description = refdes
        else:
            description = hint
        tbd = orb.get('pgefobjects:TBD')
        if obj is tbd:
            name = "TBD"
            version = ''
            self.style = Qt.DashLine
            self.color = Qt.darkGreen
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
        self.update()

    def del_usage(self):
        pass

    usage = property(get_usage, set_usage, del_usage, 'usage property')

    # def contextMenuEvent(self, event):
        # self.scene().clearSelection()
        # self.setSelected(True)
        # menu = QMenu()
        # menu.addAction('do something blockish', self.something)
        # menu.exec_(event.screenPos())

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
        self.update()
        global Dirty
        Dirty = True

    def mouseDoubleClickEvent(self, event):
        QGraphicsItem.mouseDoubleClickEvent(self, event)
        self.scene().item_doubleclick(self)

    def mousePressEvent(self, event):
        self.setSelected(True)
        QGraphicsItem.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        QGraphicsItem.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        # orb.log.debug("* ObjectBlock: mouseReleaseEvent()")
        # deselect so another object can be selected
        self.setSelected(False)
        QGraphicsItem.mouseReleaseEvent(self, event)

    def mimeTypes(self):
        return ["application/x-pgef-hardware-product"]

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        orb.log.debug("* ObjectBlock: something dropped on me ...")
        # only accept the drop if dropped item is a HardwareProduct and our
        # object is TBD
        drop_target = self.obj
        if (event.mimeData().hasFormat("application/x-pgef-hardware-product")
            and drop_target.oid == 'pgefobjects:TBD'):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, oid, _id, name, cname = data
            dropped_item = orb.get(oid)
            if dropped_item:
                # orb.log.info('  - dropped_item: "{}"'.format(name))
                dispatcher.send('product dropped on object block',
                                p=dropped_item)
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
                    QMessageBox.critical(
                                self.parentWidget(), "Product Type Check",
                                "The product you dropped is not a "
                                "{}.".format(hint or "[unspecified type]"),
                                QMessageBox.Cancel)
                    event.accept()
                else:
                    mod_objs = []
                    pt = dropped_item.product_type
                    if isinstance(usage, orb.classes['Acu']):
                        usage.component = dropped_item
                        usage.product_type_hint = pt
                        # Acu is modified -> assembly is modified
                        mod_objs.append(usage.assembly)
                    elif isinstance(usage, orb.classes['ProjectSystemUsage']):
                        usage.system = dropped_item
                        usage.system_role = pt.name
                    mod_objs.append(usage)
                    # NOTE: if the usage is an Acu, this will set mod_datetime
                    # and modifier for both the Acu and its assembly
                    for obj in mod_objs:
                        obj.mod_datetime = dtstamp()
                        obj.modifier = orb.get(state.get('local_user_oid'))
                    orb.save(mod_objs)
                    # NOTE:  setting 'usage' triggers name/desc label rewrites
                    self.usage = usage
                    # self.name_label.set_text(self.obj.name)
                    # self.description_label.set_text('[{}]'.format(
                                # self.obj.product_type.abbreviation))
                    orb.log.debug('   self.usage modified: {}'.format(
                                  self.usage.name))
                    for obj in mod_objs:
                        dispatcher.send('modified object', obj=obj)
                    event.accept()
            else:
                orb.log.info("  - dropped product not in db; nothing done.")
                event.accept()
        else:
            orb.log.info("  - dropped object was not a HardwareProduct")
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
        self.setFlags(QGraphicsItem.ItemIsFocusable)
        self.setAcceptDrops(True)
        # this apparently does work, but not what I wanted
        # self.setAcceptedMouseButtons(Qt.NoButton)
        self.rect = QRectF(0, 0, width, height)
        self.style = style or Qt.SolidLine
        self.__obj = obj   # used by the 'obj' property of Block
        self.right_ports = right_ports
        name = getattr(obj, 'name', None) or obj.id
        version = getattr(obj, 'version', '')
        if version:
            name += ' v.' + version
        if hasattr(obj, 'product_type'):
            desc = getattr(obj.product_type, 'abbreviation',
                           'Unspecified Type')
        else:
            # for now, if it doesn't have a product_type, it's a project ...
            desc = 'Project'
        description = '[{}]'.format(desc)
        # self.connectors = []
        self.setPos(position)
        self.description_label = TextLabel(description, self,
                                           color='darkMagenta')
        self.description_label.setPos(2.0 * POINT_SIZE, 0.0 * POINT_SIZE)
        name_x = 20
        name_y = self.description_label.boundingRect().height() + 5
        self.name_label = BlockLabel(name, self, centered=False, x=name_x,
                                     y=name_y)
        self.rebuild_port_blocks()
        self.update()
        # SubjectBlocks get a z-value of 0 (lower than ObjectBlocks, so
        # ObjectBlocks can receive mouse events)
        z_value = 0.0
        self.setZValue(z_value)
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
        pen = QPen(self.style)
        pen.setColor(Qt.black)
        pen.setWidth(2)
        if option.state & QStyle.State_Selected:
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
        """
        Handle the drop event on SubjectBlock.  This includes the following
        possible cases:

            0: dropped item would cause a cycle -> abort
            1: drop target is "TBD" -> replace it if drop item is a Product
               and matches the "product_type_hint" of the Acu
            2: drop target is a normal Product -> add a new component position
               with the dropped item as the new component
            3: drop target is a Project ->
               if drop item is a Product *and* it is not already in use
               on the Project, use it to create a new ProjectSystemUsage
        """
        orb.log.debug("* SubjectBlock: something dropped on me ...")
        drop_target = self.obj
        # orb.log.debug('  - target name: {}'.format(drop_target.name))
        # first, check that user has permission to modify the target
        if not 'modify' in get_perms(drop_target):
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
        elif event.mimeData().hasFormat("application/x-pgef-hardware-product"):
            data = extract_mime_data(event,
                                     "application/x-pgef-hardware-product")
            icon, obj_oid, obj_id, obj_name, obj_cname = data
            # orb.log.info("  - it is a {} ...".format(obj_cname))
            dropped_item = orb.get(obj_oid)
            if dropped_item:
                # orb.log.info('  - found in db: "{}"'.format(obj_name))
                # orb.log.info(
                    # '    sending message "product dropped on subject block"')
                dispatcher.send('product dropped on subject block',
                                p=dropped_item)
            else:
                # orb.log.info("  - dropped product oid not in db.")
                event.ignore()
            target_cname = drop_target.__class__.__name__
            if issubclass(orb.classes[target_cname],
                          orb.classes['Product']):
                # orb.log.debug('    + target is a subclass of Product ...')
                bom_oids = get_bom_oids(dropped_item)
                # check if target is same as dropped object
                # and check for cycles
                if drop_target.oid == obj_oid:
                    # orb.log.debug(
                      # '    invalid: dropped object same as target object.')
                    popup = QMessageBox(
                                QMessageBox.Critical,
                                "Assembly same as Component",
                                "A product cannot be a component of itself.",
                                QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                elif (drop_target.oid in bom_oids and
                      drop_target.oid != 'pgefobjects:TBD'):
                    # dropped object would cause a cycle -> abort
                    popup = QMessageBox(
                            QMessageBox.Critical,
                            "Prohibited Operation",
                            "Product cannot be used in its own assembly.",
                            QMessageBox.Ok, self.parentWidget())
                    popup.show()
                    event.ignore()
                else:
                    # add new Acu
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
                        reference_designator=ref_des)
                    # new Acu -> drop target is modified (any computed
                    # parameters must be recomputed, etc.)
                    drop_target.mod_datetime = dtstamp()
                    drop_target.modifier = orb.get(state.get('local_user_oid'))
                    orb.save([new_acu, drop_target])
                    # orb.log.debug('      Acu created: {}'.format(
                                  # new_acu.name))
                    self.scene().create_block(ObjectBlock, usage=new_acu)
                    dispatcher.send('new object', obj=new_acu)
                    dispatcher.send('modified object', obj=drop_target)
            elif target_cname == 'Project':
                # case 3: drop target is a project
                # log_txt = '+ target is a Project -- creating PSU ...'
                # orb.log.debug('    {}'.format(log_txt))
                psu = orb.search_exact(cname='ProjectSystemUsage',
                                       project=drop_target,
                                       system=dropped_item)
                if psu:
                    QMessageBox.warning(self.parentWidget(),
                                    'Already exists',
                                    'System "{0}" already exists on '
                                    'project {1}'.format(
                                    dropped_item.name, drop_target.id))
                else:
                    psu_id = ('psu-' + dropped_item.id + '-' +
                              drop_target.id)
                    psu_name = ('psu: ' + dropped_item.name +
                                ' (system used on) ' + drop_target.name)
                    psu_role = getattr(dropped_item.product_type, 'name',
                                       'System')
                    new_psu = clone('ProjectSystemUsage',
                                    id=psu_id,
                                    name=psu_name,
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
            data = extract_mime_data(event, "application/x-pgef-port-type")
            icon, oid, _id, name, cname = data
            # orb.log.info("  - it is a {} ...".format(cname))
            port_type = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                # orb.log.info("  - {} cannot have ports.".format(
                                                # self.obj.__class__.__name__))
                event.ignore()
            elif port_type:
                # orb.log.info('  - orb found {} "{}"'.format(cname, name))
                # orb.log.info('    creating Port ...')
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
                # orb.log.info("  - dropped port type oid not in db.")
                event.ignore()
        elif event.mimeData().hasFormat("application/x-pgef-port-template"):
            data = extract_mime_data(event, "application/x-pgef-port-template")
            icon, oid, _id, name, cname = data
            # orb.log.info("  - it is a {} ...".format(cname))
            port_template = orb.get(oid)
            if not hasattr(self.obj, 'ports'):
                # orb.log.info("  - {} cannot have ports.".format(
                                                # self.obj.__class__.__name__))
                event.ignore()
            elif port_template:
                # orb.log.info('  - orb found {} "{}"'.format(cname, name))
                # orb.log.info('    creating Port ...')
                port_type = port_template.type_of_port
                seq = get_next_port_seq(self.obj, port_type)
                port_id = get_port_id(port_type.id, seq)
                port_name = get_port_name(port_type.name, seq)
                port_desc = port_template.description
                new_port = clone('Port', id=port_id, name=port_name,
                                 abbreviation=port_name, description=port_desc,
                                 type_of_port=port_type, of_product=self.obj)
                orb.db.commit()
                # if the port_template has parameters, add them to the new port
                if parameterz.get(port_template.oid):
                    new_parameters = parameterz[port_template.oid].copy()
                    parameterz[new_port.oid] = new_parameters
                dispatcher.send('new object', obj=new_port)
                self.obj.mod_datetime = dtstamp()
                self.obj.modifier = orb.get(state.get('local_user_oid'))
                orb.save([self.obj])
                dispatcher.send('modified object', obj=self.obj)
                self.rebuild_port_blocks()
            else:
                orb.log.info("  - dropped port template oid not in db.")
                event.ignore()
        else:
            orb.log.info("  - dropped object is not an allowed type")
            orb.log.info("    to drop on object block.")


class PortBlock(QGraphicsItem):
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
                      # QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemIsFocusable)
        self.setAcceptHoverEvents(True)
        tooltip_text = port.abbreviation or port.name
        self.setToolTip(tooltip_text)
        self.rect = QRectF(0, -POINT_SIZE, PORT_SIZE, PORT_SIZE)
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
        return self.parent_block.parentWidget()

    def contextMenuEvent(self, event):
        if isinstance(self.parent_block, SubjectBlock):
            perms = get_perms(self.port)
            self.scene().clearSelection()
            # self.setSelected(True)
            menu = QMenu()
            menu.addAction('inspect port object', self.open_pxo)
            if 'delete' in perms:
                menu.addAction('delete port', self.delete)
            menu.exec_(event.screenPos())
        else:
            event.ignore()

    def delete(self):
        txt = 'This will delete the {}'.format(self.port.name)
        txt += ' and any associated Flow(s) -- are you sure?'
        confirm_dlg = QMessageBox(QMessageBox.Question, 'Delete Port?', txt,
                                  QMessageBox.Yes | QMessageBox.No)
        response = confirm_dlg.exec_()
        if response == QMessageBox.Yes:
            # delete connector(s) and their associated flows, if any ...
            for shape in self.scene().items():
                if (isinstance(shape, RoutedConnector) and
                    (shape.start_item is self or shape.end_item is self)):
                    orb.delete([shape.flow])
                    self.shape.prepareGeometryChange()
                    self.scene().removeItem(shape)
            # the PortBlock must have a Port, but check just to be sure ...
            if getattr(self, 'port', None):
                orb.delete([self.port])
            # finally, delete the PortBlock itself ...
            parent_block = self.parent_block
            self.prepareGeometryChange()
            self.scene().removeItem(self)
            parent_block.rebuild_port_blocks()

    def open_pxo(self):
        dlg = PgxnObject(self.port, modal_mode=True,
                         parent=self.parentWidget())
        dlg.show()

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
        painter.drawRect(self.rect)

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
            connector.prepareGeometryChange()
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
        self.name_label = BlockLabel(name, self, editable=editable)
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
        super(RoutedConnector, self).__init__()
        self.segments = []
        self.routing_channel = routing_channel
        # default is Electrical Power (red)
        self.type_of_flow = getattr(start_item.port.type_of_port, 'id',
                                    'electrical_power')
        self.color = PORT_TYPE_COLORS[self.type_of_flow]
        self.pen = QPen(self.color, pen_width, Qt.SolidLine, Qt.RoundCap,
                        Qt.RoundJoin)
        self.start_item = start_item
        self.end_item = end_item
        self.context = context
        # check whether user has permission to modify the 'context' object
        if not 'modify' in get_perms(context):
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
            return
        self.setAcceptHoverEvents(True)
        self.arrow = arrow
        self.pen_width = pen_width
        self.normal_pen_width = pen_width
        self.wide_pen_width = pen_width + 5
        if arrow:
            self.arrow_head = QPolygonF()
        # 'paints' is for dev analysis -- number of calls to paint()
        # self.paints = 0
        flows = orb.search_exact(start_port=start_item.port,
                                 end_port=end_item.port)
        if flows:
            # TODO:  check for errors (e.g. multiple flows)
            self.flow = flows[0]  # *should* only be one ...
        else:
            self.flow = clone('Flow',
                id=get_flow_id(start_item.port.id, end_item.port.id),
                name=get_flow_name(start_item.port.name, end_item.port.name),
                start_port=start_item.port, end_port=end_item.port,
                flow_context=context)
            orb.db.commit()
            # new Flow -> context object is modified
            context.mod_datetime = dtstamp()
            context.modifier = orb.get(state.get('local_user_oid'))
            orb.save([context])
            dispatcher.send('modified object', obj=context)
        # orb.log.debug("* RoutedConnector created:")
        # orb.log.debug("  - start port id: {}".format(self.start_item.port.id))
        # orb.log.debug("  - end port id: {}".format(self.end_item.port.id))
        # orb.log.debug("  - context id: {}".format(self.context.id))

    def contextMenuEvent(self, event):
        self.scene().clearSelection()
        self.setSelected(True)
        menu = QMenu()
        menu.addAction('delete connector', self.delete)
        menu.exec_(event.screenPos())

    def delete(self):
        # check whether user has permission to modify the 'context' object
        if not 'modify' in get_perms(self.context):
            popup = QMessageBox(
                  QMessageBox.Critical,
                  "Unauthorized Operation",
                  "User's roles do not permit this operation",
                  QMessageBox.Ok, self.parentWidget())
            popup.show()
            return
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
                dispatcher.send('deleted object', obj=self.flow.oid,
                                cname='Flow')
                orb.delete([self.flow])
            self.start_item.remove_connector(self)
            self.end_item.remove_connector(self)
            self.scene().removeItem(self)
            # deleted Flow -> context object is modified
            self.context.mod_datetime = dtstamp()
            self.context.modifier = orb.get(state.get('local_user_oid'))
            orb.save([self.context])
            dispatcher.send('modified object', obj=self.context)

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
        return QRectF(p1, QSizeF(p2.x() - p1.x(), p2.y() - p1.y())
                      ).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        if self.segments:
            path = QPainterPath()
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
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
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
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
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
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
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
                seg1p1x = start_item.scenePos().x() + start_x_pad
                seg1p2x = seg1p1x + x_jog
                seg1p1y = start_item.scenePos().y()
                # seg3p2x = seg1p2x - x_jog - start_x_pad + end_x_pad
                seg3p2x = end_item.scenePos().x()
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
            # seg3 is horizontal
            seg3p2y = seg2p2y
            seg2p1 = seg1p2
            seg2p2 = QPointF(seg2p2x, seg2p2y)
            seg3p1 = seg2p2
            seg3p2 = QPointF(seg3p2x, seg3p2y)
            seg1p1 = QPointF(seg1p1x, seg1p1y)
            seg1p2 = QPointF(seg1p2x, seg1p1y)
            # seg2 is vertical
            seg2p2x = seg1p2x
            seg2p2y = end_item.scenePos().y()
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
        # super(RoutedConnector, self).hoverEnterEvent(event)
        # orb.log.debug("RoutedConnector hover enter...")
        # self.pen_width = self.wide_pen_width
        # self.update()

    # def hoverLeaveEvent(self, event):
        # super(RoutedConnector, self).hoverLeaveEvent(event)
        # orb.log.debug("RoutedConnector hover leave ...")
        # self.pen_width = self.normal_pen_width
        # self.update()


class BlockLabel(QGraphicsTextItem):
    """
    Label for a block "name", which may contain spaces (and therefore may be
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
    def __init__(self, text, parent, font_name=None, point_size=None,
                 weight=None, color=None, centered=True, x=None, y=None):
        super(BlockLabel, self).__init__(parent=parent)
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
        editable (bool):  whether the text should be editable
    """
    # TODO:  add scrolling capability
    def __init__(self, text, parent, font=QFont("Arial", POINT_SIZE),
                 color=None, editable=False):
        # if nowrap:
            # textw = text
        # else:
            # textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super(TextLabel, self).__init__(parent=parent)
        # if not nowrap:
        self.text_option = QTextOption()
        self.text_option.setWrapMode(QTextOption.WordWrap)
        self.document().setDefaultTextOption(self.text_option)
        self.setTextWidth(parent.boundingRect().width() - 50)
        self.setFont(font)
        if color in QTCOLORS:
            self.setDefaultTextColor(getattr(Qt, color))
        if editable:
            self.setFlags(QGraphicsItem.ItemIsSelectable)
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

    def mouseDoubleClickEvent(self, event):
        dialog = TextItemDlg(self, self.parentWidget())
        dialog.exec_()


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
        editable (bool):  whether the text should be editable
    """
    # TODO:  add scrolling capability
    def __init__(self, text, position, scene,
                 font=QFont("Arial", POINT_SIZE),
                 color=None):
        textw = '\n'.join(wrap(text, width=25, break_long_words=False))
        super(TextItem, self).__init__(textw)
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

    def mouseDoubleClickEvent(self, event):
        dialog = TextItemDlg(self, self.parentWidget())
        dialog.exec_()


class TextItemDlg(QDialog):

    def __init__(self, item=None, position=None, scene=None, parent=None):
        super(QDialog, self).__init__(parent)
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
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setTabChangesFocus(True)
        self.editorLabel = QLabel("&Text:")
        self.editorLabel.setBuddy(self.editor)
        self.fontComboBox = QFontComboBox()
        self.fontComboBox.setCurrentFont(QFont("Arial", POINT_SIZE))
        self.fontLabel = QLabel("&Font:")
        self.fontLabel.setBuddy(self.fontComboBox)
        self.fontSpinBox = QSpinBox()
        self.fontSpinBox.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.fontSpinBox.setRange(6, 280)
        self.fontSpinBox.setValue(POINT_SIZE)
        self.fontSizeLabel = QLabel("&Size:")
        self.fontSizeLabel.setBuddy(self.fontSpinBox)
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok |
                                          QDialogButtonBox.Cancel)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)

        if self.item is not None:
            self.editor.setPlainText(self.item.toPlainText())
            self.fontComboBox.setCurrentFont(self.item.font())
            self.fontSpinBox.setValue(self.item.font().pointSize())

    def layout_widgets(self):
        layout = QGridLayout()
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
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(
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
        QDialog.accept(self)
