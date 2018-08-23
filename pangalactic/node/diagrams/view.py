"""
A diagram scene and view
"""
import platform, random
from PyQt5.QtGui     import QFont
from PyQt5.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsScene,
                             QGraphicsView, QMessageBox, QSizePolicy)
from PyQt5.QtCore    import Qt, QLineF, QPoint, QPointF, QRectF, pyqtSignal

from louie import dispatcher

# pangalactic
from pangalactic.core.uberorb import orb
from pangalactic.node.diagrams.shapes import (ObjectBlock, PortBlock,
                                              RoutedConnector, SubjectBlock)


class DiagramScene(QGraphicsScene):
    """
    The scene of a diagram
    """
    insert_item, insert_connector, move_item  = range(3)
    item_inserted = pyqtSignal(ObjectBlock)
    item_selected = pyqtSignal(QGraphicsItem)
    default_item_color = Qt.white
    default_text_color = Qt.black
    default_line_color = Qt.black
    default_font = QFont()

    def __init__(self, subject, parent=None):
        """
        Initialize.

        Args:
            subject (ManagedObject):  object that is the subject of the diagram
        """
        super(DiagramScene, self).__init__(parent)
        w = 1600
        h = 2400
        self.setSceneRect(QRectF(0, 0, w, h))
        self.subject = subject
        self.moves = 0
        self.current_mode = self.move_item
        self.line = None
        self.prev_point = QPoint()
        self.item_inserted.connect(self.process_item_inserted)
        self.item_selected.connect(self.process_item_selected)

    def new_position(self):
        coord = random.randint(36, 144)
        point = QPoint(coord, coord)
        return self.parent().mapToScene(point)

    def create_item(self, item_type, obj=None, pos=None, width=None,
                    height=None, right_ports=False):
        # TODO: define item types ... for now, ignore ...
        if not pos:
            # NOTE:  for now, new_position() selects a random position ...
            pos = self.new_position()
        if not item_type or item_type is ObjectBlock:
            item = ObjectBlock(pos, scene=self, obj=obj,
                               right_ports=right_ports)
            self.item_inserted.emit(item)
        elif item_type is SubjectBlock:
            w = width or 100
            h = height or 50
            # ports, if any, are on the right by default for SubjectBlock
            item = SubjectBlock(pos, scene=self, obj=obj, width=w, height=h)
        self.clearSelection()
        return item

    def delete_item(self):
        for item in self.selectedItems():
            if isinstance(item, PortBlock):
                item.remove_connectors()
            self.removeItem(item)

    def process_item_selected(self, item):
        # TODO:  figure out appropriate highlighting of item, etc.
        pass

    def process_item_inserted(self, item):
        # TODO:  what to do about item being inserted
        self.current_mode = self.move_item

    def setLineColor(self, color):
        self.default_line_color = color
        if self.isItemChange(RoutedConnector):
            item = self.selectedItems()[0]
            item.setColor(self.default_line_color)
            self.update()

    def setItemColor(self, color):
        color = color or self.default_item_color
        if self.isItemChange(ObjectBlock):
            item = self.selectedItems()[0]
            item.setBrush(color)

    def setMode(self, mode):
        self.current_mode = mode

    def editorLostFocus(self, item):
        cursor = item.textCursor()
        cursor.clearSelection()
        item.setTextCursor(cursor)

        if item.toPlainText():
            self.removeItem(item)
            item.deleteLater()

    def mousePressEvent(self, mouseEvent):
        if (mouseEvent.button() != Qt.LeftButton):
            return
        down_items = self.items(mouseEvent.scenePos())
        candidate_items = [i for i in down_items
                           if hasattr(i, 'add_connector')]
        if candidate_items:
            self.current_mode = self.insert_connector
            # NOTE:  in connector-drawing mode ("insert_connector"), if the
            # selected item does not support connectors (e.g. ObjectBlock),
            # discard the event (otherwise, item will be moved rather than
            # having a connector drawn -- probably not what the user wants)
            self.line = QGraphicsLineItem(QLineF(mouseEvent.scenePos(),
                                                 mouseEvent.scenePos()))
            # self.line.setPen(QPen(self.default_line_color, 2))
            # self.clearSelection()
            self.addItem(self.line)
        else:
            # if NOT in connector-drawing mode, re-issue the event
            super(DiagramScene, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        self.moves += 1
        if self.current_mode == self.insert_connector and self.line:
            newLine = QLineF(self.line.line().p1(), mouseEvent.scenePos())
            self.line.setLine(newLine)
            self.update()
        else:
            super(DiagramScene, self).mouseMoveEvent(mouseEvent)
            # AHA!!!!!  doing self.update() forces the refresh!! :D
            self.update()

    def mouseReleaseEvent(self, mouseEvent):
        if self.line:
            orb.log.debug(' - mouseReleaseEvent ...')
            down_items = self.items(self.line.line().p1())
            start_items = [i for i in down_items if isinstance(i, PortBlock)]
            if start_items:
                orb.log.debug('   start_items: %s' % start_items[0].obj.id)
            up_items = self.items(self.line.line().p2())
            end_items = [i for i in up_items if isinstance(i, PortBlock)]
            if end_items:
                orb.log.debug('   end_items: %s' % end_items[0].obj.id)
            self.removeItem(self.line)
            self.line = None
            if (len(start_items) and len(end_items)
                and start_items[0] != end_items[0]):
                start_item = start_items[0]
                end_item = end_items[0]
                orb.log.debug("  - start port type: {}".format(
                                            start_item.port.type_of_port.id))
                orb.log.debug("  - end port type: {}".format(
                                            end_item.port.type_of_port.id))
                if start_item.port.type_of_port.id != end_item.port.type_of_port.id:
                    txt = 'Cannot connect ports of different types.'
                    notice = QMessageBox()
                    notice.setText(txt)
                    notice.exec_()
                    return
                orb.log.debug('   drawing RoutedConnector ...')
                orb.log.debug('   * start item:')
                orb.log.debug('     - object id: {}'.format(start_item.obj.id))
                orb.log.debug('     - port id: {}'.format(start_item.port.id))
                side = 'right'
                if start_item.right_port:
                    side = 'left'
                orb.log.debug('     ({} side)'.format(side))
                orb.log.debug('   * end item:')
                orb.log.debug('     - object id: {}'.format(end_item.obj.id))
                orb.log.debug('     - port id: {}'.format(end_item.port.id))
                orb.log.debug('   * context id:  {}'.format(self.subject.id))
                side = 'right'
                if end_item.right_port:
                    side = 'left'
                orb.log.debug('     ({} side)'.format(side))
                # TODO:  color will be determined by the type of the Port(s)
                connector = RoutedConnector(start_item, end_item,
                                            context=self.subject, pen_width=3)
                start_item.add_connector(connector)
                end_item.add_connector(connector)
                connector.setZValue(-1000.0)
                self.addItem(connector)
                connector.updatePosition()
                dispatcher.send('diagram connector added',
                                start_item=start_item, end_item=end_item)
                self.update()
            self.current_mode = self.move_item
        self.line = None
        super(DiagramScene, self).mouseReleaseEvent(mouseEvent)

    def isItemChange(self, type):
        for item in self.selectedItems():
            if isinstance(item, type):
                return True
        return False

    def item_doubleclick(self, item):
        """
        Drill down to next level block diagram
        """
        # NOTE:  drill-down so far only applies to ObjectBlock, and *not* to
        # SubjectBlock (a subclass)
        orb.log.info('* DiagramScene: item_doubleclick()')
        if platform.platform().startswith('Darwin'):
            # drill-down currently crashes on OSX
            orb.log.info('  - Mac does not like this -- ignoring.')
            return
        if isinstance(item, SubjectBlock):
            return
        elif isinstance(item, ObjectBlock):
            obj = item.obj
            dispatcher.send('diagram object drill down', obj=obj)

    def get_routing_channel(self):
        """
        Return the left and right x-coordinates within which the vertical
        segments of connectors are to be drawn.
        """
        # find all the object blocks and group them by left and right
        left_xs = []
        right_xs = []
        for shape in self.items():
            if isinstance(shape, ObjectBlock):
                rp = getattr(shape, 'right_ports', False)
                if rp:
                    left_xs.append(shape.x() + shape.rect.width())
                else:
                    right_xs.append(shape.x())
        left_x = max(left_xs or [300])
        right_x = min(right_xs or [400])
        return left_x, right_x

    def create_ibd_subject_block(self, items):
        """
        Create the SubjectBlock for an Internal Block Diagram (IBD).

        Args:
            items (list of ObjectBlock): blocks to be enclosed
        """
        orb.log.info('* DiagramScene: create_ibd_subject_block()')
        if items:
            item_group = self.createItemGroup(items)
            orb.log.info('  - DiagramScene: created item group ...')
            brect = item_group.boundingRect()
            sb_width = brect.width() + 150
            sb_height = brect.height() + 150
        else:
            # if empty, give it minimum w, h
            sb_width = 300
            sb_height = 300
        return self.create_item(SubjectBlock, obj=self.subject,
                                pos=QPointF(20, 20),
                                width=sb_width, height=sb_height)

    def create_ibd(self, objs):
        """
        Create an Internal Block Diagram (IBD) for a list of objects.

        Args:
            objs (list of Modelables): objects to create blocks for
        """
        orb.log.info('* DiagramScene: create_ibd()')
        # TODO:  use actual block widths/heights in placement algorithm ... for
        # now, use some defaults for simplification
        w = 100
        h = 150
        i = 1.0
        y_left_next = y_right_next = h
        spacing = 20
        items = []
        all_ports = []
        port_blocks = {}   # maps Port oids to PortBlock instances
        # create component blocks in 2 vertical columns
        for obj in objs:
            all_ports += obj.ports
            orb.log.info('  - creating block for "%s" ...' % obj.name)
            if i == 2.0:
                left_col = right_ports = False
                p = QPointF(7*w, y_right_next)
                i = 1.0
            else:
                left_col = right_ports = True
                p = QPointF(w, y_left_next)
                i += 1.0
            orb.log.info('    ... at position (%s, %s) ...' % (str(p.x()),
                                                               str(p.y())))
            new_item = self.create_item(ObjectBlock, obj=obj, pos=p,
                                        right_ports=right_ports)
            items.append(new_item)
            if left_col:
                y_left_next += new_item.rect.height() + spacing
            else:
                y_right_next += new_item.rect.height() + spacing
            port_blocks.update(new_item.port_blocks)
        # create subject block ...
        subj_block = self.create_ibd_subject_block(items)
        port_blocks.update(subj_block.port_blocks)
        # if Flows exist, create RoutedConnectors for them ...
        # subject might be a Project, so need getattr here ...
        all_ports += getattr(self.subject, 'ports', [])
        # FIXME: finding the flows by getting ALL Flows from the db and going
        # through them is ok if db is small but will not scale!  Create an
        # optimized db query for this ...
        known_flows = orb.get_by_type('Flow')
        all_flows = [flow for flow in known_flows
                     if (flow.start_port in all_ports and
                         flow.end_port in all_ports and
                         flow.flow_context == self.subject)]
        for flow in all_flows:
            start_item = port_blocks[flow.start_port.oid]
            end_item = port_blocks[flow.end_port.oid]
            connector = RoutedConnector(start_item, end_item,
                                        context=self.subject, pen_width=3)
            start_item.add_connector(connector)
            end_item.add_connector(connector)
            connector.setZValue(-1000.0)
            self.addItem(connector)
            connector.updatePosition()
        # set the upper left corner scene ...
        diag_view = self.views()[0]
        diag_view.centerOn(0, 0)

    def save_diagram(self):
        """
        Return a serialization of the current block diagram (in the form of a
        structured dict).
        """
        orb.log.info('* DiagramScene: save_diagram()')
        object_blocks = {}
        subject_block = {}
        flows = []
        for shape in self.items():
            if isinstance(shape, ObjectBlock):
                x = shape.x()
                y = shape.y()
                rp = getattr(shape, 'right_ports', False)
                orb.log.debug('* ObjectBlock at {}, {}'.format(x, y))
                object_blocks[shape.obj.oid] = dict(x=x, y=y, right_ports=rp)
            ## Instantiating the ObjectBlock will recreate its PortBlocks
            ## automatically, and RoutedConnectors will know their start/end
            ## PortBlocks' associated Port oids.
            ## TODO: need to specify positions of PortBlocks (positions should
            ## be modifiable by preference or for routing)
            # elif isinstance(shape, PortBlock):
                # port_blocks.append(shape)
            elif isinstance(shape, RoutedConnector):
                start = shape.start_item.port.oid
                end = shape.end_item.port.oid
                context = getattr(shape.context, 'oid', '')
                flows.append(dict(start=start, end=end, context=context))
                orb.log.debug('* flow saved:')
                orb.log.debug('    start port = {}'.format(start))
                orb.log.debug('    end port = {}'.format(end))
                orb.log.debug('    context = {}'.format(context))
            else:
                # this gets very verbose ...
                # orb.log.debug('* %s at %s not saved' %
                              # (str(type(shape)), str(shape.pos())))
                pass
        # check on routing channel ...
        orb.log.debug('* routing channel: {}'.format(
                                                self.get_routing_channel()))
        return dict(object_blocks=object_blocks,
                    subject_block=subject_block,
                    flows=flows)

    def restore_diagram(self, model, objs):
        """
        Recreate a block diagram from a saved model, ensuring that blocks for
        all objects in 'objs' are included.

        Args:
            model (dict): a serialized block model
            objs (list of Modelables): component objects to create
                object_blocks for
        """
        # TODO:  include objs (add blocks for any missing ones)
        orb.log.info('* DiagramScene: restore_diagram()')
        port_blocks = {}   # maps Port oids to PortBlock instances
        object_blocks = []
        y_left_last = y_right_last = 0  # y coord of tops of last blocks
        y_left_next = y_right_next = 150 # y of top of next blocks
        spacing = 20
        w = 100
        if objs:
            objs_by_oid = {o.oid : o for o in objs}
            if model.get('object_blocks'):
                for oid, item in model['object_blocks'].items():
                    # first restore ObjectBlocks -- ports created automatically
                    # if the "obj" has a non-null "ports" attribute
                    if oid in objs_by_oid:
                        # if in objs, get the object and remove it from objs
                        obj = objs_by_oid[oid]
                        del objs_by_oid[oid]
                    else:
                        # if not, ignore it (do not include it in the diagram)
                        continue
                    orb.log.info('  - creating block "{}" ...'.format(
                                                                    obj.name))
                    x, y = item['x'], item['y']
                    p = QPointF(x, y)
                    orb.log.info('    ... at position (%s, %s) ...' % (str(x),
                                                                       str(y)))
                    rp = item.get('right_ports', False)
                    obj_block = self.create_item(None, obj=obj, pos=p,
                                                 right_ports=rp)
                    port_blocks.update(obj_block.port_blocks)
                    object_blocks.append(obj_block)
                    if rp:
                        if y > y_left_last:
                            y_left_last = y
                            y_left_next = y + obj_block.rect.height() + spacing
                    else:
                        if y > y_right_last:
                            y_right_last = y
                            y_right_next = (y + obj_block.rect.height()
                                            + spacing)
            for obj in objs_by_oid.values():
                # create blocks for missing objs, if any
                orb.log.info('  - adding missing block "{}" ...'.format(
                                                                    obj.name))
                if y_left_next <= y_right_next:
                    # left col is shorter or same so add next block there ...
                    p = QPointF(w, y_left_next)
                    rp = True
                else:
                    # right col is shorter ...
                    p = QPointF(7*w, y_right_next)
                    rp = False
                obj_block = self.create_item(None, obj=obj, pos=p,
                                             right_ports=rp)
                port_blocks.update(obj_block.port_blocks)
                object_blocks.append(obj_block)
                if rp:
                    y_left_next += obj_block.rect.height() + spacing
                else:
                    y_right_next += obj_block.rect.height() + spacing
        # SubjectBlock is always created, whether there are ObjectBlocks or not
        subj_block = self.create_ibd_subject_block(object_blocks)
        port_blocks.update(subj_block.port_blocks)
        for flow in model['flows']:
            start_item = port_blocks.get(flow['start'])
            end_item = port_blocks.get(flow['end'])
            if start_item and end_item:
                # TODO:  color will be determined by the type of the Port(s)
                connector = RoutedConnector(start_item, end_item,
                                            context=self.subject, pen_width=3)
                start_item.add_connector(connector)
                end_item.add_connector(connector)
                connector.setZValue(-1000.0)
                self.addItem(connector)
                connector.updatePosition()
        # check on routing channel ...
        orb.log.debug('* routing channel: {}'.format(
                                                self.get_routing_channel()))
        # center the view on the upper left of the scene ...
        diag_view = self.views()[0]
        diag_view.centerOn(0, 0)

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


class DiagramView(QGraphicsView):
    """
    A view with a room.  :)
    """
    def __init__(self, subject, embedded=False, scene=None, parent=None):
        """
        Initialize.

        Args:
            subject (ManagedObject):  object that is the subject of the diagram

        Keyword Args:
            embedded (bool): flag to indicate the view is embedded and should
                not get an 'exit' menu item
            scene (DiagramScene): scene to be used
        """
        super(DiagramView, self).__init__()
        scene = scene or DiagramScene(subject, parent=self)
        self.setScene(scene)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Expanding)
        self.setMinimumSize(300, 300)
        self.setAcceptDrops(True)

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

    # def dropEvent(self, event):
        # orb.log.debug("* DiagramView: something dropped on me ...")
        # if event.mimeData().hasFormat(
                                # "application/x-pgef-hardware-product"):
            # orb.log.info("  - it is a hardware product ...")
            # data = extract_mime_data(event, 
                                     # "application/x-pgef-hardware-product")
            # icon, p_oid, p_id, p_name, p_cname = data
            # product = orb.get(p_oid)
            # if product:
                # orb.log.info(
                    # '  - orb found oid, sending message "drop on diagram"')
                # dispatcher.send('drop on diagram', p=product)
            # else:
                # event.ignore()
                # orb.log.info("  - dropped product oid not in db.")
        # else:
            # orb.log.info("  - dropped product oid not in db.")


