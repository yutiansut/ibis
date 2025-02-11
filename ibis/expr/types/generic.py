from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence

if TYPE_CHECKING:
    import ibis.expr.types as ir
    import ibis.expr.operations as ops
    import ibis.expr.window as win

from public import public

import ibis
import ibis.common.exceptions as com

from .. import datatypes as dt
from .core import Expr, _binop


@public
class ValueExpr(Expr):
    """Base class for an expression having a known type."""

    _name: str | None
    _dtype: dt.DataType

    def __init__(
        self,
        arg: ops.ValueOp,
        dtype: dt.DataType,
        name: str | None = None,
    ) -> None:
        super().__init__(arg)
        self._name = name
        self._dtype = dtype

    def equals(self, other):
        if not isinstance(other, Expr):
            raise TypeError(
                "invalid equality comparison between Expr and "
                f"{type(other)}"
            )
        return (
            self._safe_name == other._safe_name
            and self._dtype.equals(other._dtype)
            and super().equals(other)
        )

    def has_name(self) -> bool:
        if self._name is not None:
            return True
        return self.op().has_resolved_name()

    def get_name(self) -> str:
        if self._name is not None:
            # This value has been explicitly named
            return self._name

        # In some but not all cases we can get a name from the node that
        # produces the value
        return self.op().resolve_name()

    def name(self, name: str) -> ValueExpr:
        """Rename an expression to `name`.

        Parameters
        ----------
        name
            The new name of the expression

        Returns
        -------
        ValueExpr
            `self` with name `name`

        Examples
        --------
        >>> import ibis
        >>> t = ibis.table(dict(a="int64"))
        >>> t.a.name("b")
        r0 := UnboundTable[unbound_table_...]
          a int64
        b: r0.a
        """
        return self._factory(self._arg, name=name)

    def type(self) -> dt.DataType:
        """Return the data type of an expression.

        Returns
        -------
        DataType
            Type of the expression
        """
        return self._dtype

    @property
    def _factory(self) -> Callable[[ops.ValueOp, str | None], ValueExpr]:
        def factory(arg: ops.ValueOp, name: str | None = None) -> ValueExpr:
            return type(self)(arg, dtype=self.type(), name=name)

        return factory


@public
class ScalarExpr(ValueExpr):
    def to_projection(self):
        """
        Promote this column expression to a table projection
        """
        from .relations import TableExpr

        roots = self.op().root_tables()
        if len(roots) > 1:
            raise com.RelationError(
                'Cannot convert scalar expression '
                'involving multiple base table references '
                'to a projection'
            )

        table = TableExpr(roots[0])
        return table.projection([self])

    def _repr_html_(self) -> str | None:
        return None


@public
class ColumnExpr(ValueExpr):
    def parent(self):
        return self._arg

    def to_projection(self):
        """
        Promote this column expression to a table projection
        """
        from .relations import TableExpr

        roots = self.op().root_tables()
        if len(roots) > 1:
            raise com.RelationError(
                'Cannot convert array expression '
                'involving multiple base table references '
                'to a projection'
            )

        table = TableExpr(roots[0])
        return table.projection([self])

    def _repr_html_(self) -> str | None:
        if not ibis.options.interactive:
            return None

        return self.execute().to_frame()._repr_html_()


@public
class AnyValue(ValueExpr):
    def hash(self, how: str = "fnv") -> ir.IntegerValue:
        """Compute an integer hash value.

        Parameters
        ----------
        how
            Hash algorithm to use

        Returns
        -------
        IntegerValue
            The hash value of `self`
        """
        import ibis.expr.operations as ops

        return ops.Hash(self, how).to_expr()

    def cast(self, target_type: dt.DataType) -> ValueExpr:
        """Cast expression to indicated data type.

        Parameters
        ----------
        target_type
            Type to cast to

        Returns
        -------
        ValueExpr
            Casted expression
        """
        import ibis.expr.operations as ops

        op = ops.Cast(self, to=target_type)

        if op.to.equals(self.type()):
            # noop case if passed type is the same
            return self

        if isinstance(op.to, (dt.Geography, dt.Geometry)):
            from_geotype = self.type().geotype or 'geometry'
            to_geotype = op.to.geotype
            if from_geotype == to_geotype:
                return self

        result = op.to_expr()
        if not self.has_name():
            return result
        return result.name(f'cast({self.get_name()}, {op.to})')

    def coalesce(self, *args: ValueExpr) -> ValueExpr:
        """Return the first non-null value from `args`.

        Parameters
        ----------
        args
            Arguments from which to choose the first non-null value

        Returns
        -------
        ValueExpr
            Coalesced expression

        Examples
        --------
        >>> import ibis
        >>> expr1 = None
        >>> expr2 = 4
        >>> result = ibis.coalesce(expr1, expr2, 5)
        """
        import ibis.expr.operations as ops

        return ops.Coalesce([self, *args]).to_expr()

    def greatest(self, *args: ir.ValueExpr) -> ir.ValueExpr:
        """Compute the largest value among the supplied arguments.

        Parameters
        ----------
        args
            Arguments to choose from

        Returns
        -------
        ValueExpr
            Maximum of the passed arguments
        """
        import ibis.expr.operations as ops

        return ops.Greatest([self, *args]).to_expr()

    def least(self, *args: ir.ValueExpr) -> ir.ValueExpr:
        """Compute the smallest value among the supplied arguments.

        Parameters
        ----------
        args
            Arguments to choose from

        Returns
        -------
        ValueExpr
            Minimum of the passed arguments
        """
        import ibis.expr.operations as ops

        return ops.Least([self, *args]).to_expr()

    def typeof(self) -> ir.StringValue:
        """Return the data type of the expression.

        The values of the returned strings are necessarily backend dependent.

        Returns
        -------
        StringValue
            A string indicating the type of the value
        """
        import ibis.expr.operations as ops

        return ops.TypeOf(self).to_expr()

    def fillna(self, fill_value: ScalarExpr) -> ValueExpr:
        """Replace any null values with the indicated fill value.

        Parameters
        ----------
        fill_value
            Value with which to replace `NA` values in `self`

        Examples
        --------
        >>> import ibis
        >>> table = ibis.table([('col', 'int64'), ('other_col', 'int64')])
        >>> result = table.col.fillna(5)
        >>> result2 = table.col.fillna(table.other_col * 3)

        Returns
        -------
        ValueExpr
            `self` filled with `fill_value` where it is `NA`
        """
        import ibis.expr.operations as ops

        return ops.IfNull(self, fill_value).to_expr()

    def nullif(self, null_if_expr: ValueExpr) -> ValueExpr:
        """Set values to null if they equal the values `null_if_expr`.

        Commonly use to avoid divide-by-zero problems by replacing zero with
        `NULL` in the divisor.

        Parameters
        ----------
        null_if_expr
            Expression indicating what values should be NULL

        Returns
        -------
        ValueExpr
            Value expression
        """
        import ibis.expr.operations as ops

        return ops.NullIf(self, null_if_expr).to_expr()

    def between(
        self,
        lower: ValueExpr,
        upper: ValueExpr,
    ) -> ir.BooleanValue:
        """Check if this expression is between `lower` and `upper`, inclusive.

        Parameters
        ----------
        lower
            Lower bound
        upper
            Upper bound

        Returns
        -------
        BooleanValue
            Expression indicating membership in the provided range
        """
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return ops.Between(self, rlz.any(lower), rlz.any(upper)).to_expr()

    def isin(
        self,
        values: ValueExpr | Sequence[ValueExpr],
    ) -> ir.BooleanValue:
        """Check whether this expression's values are in `values`.

        Parameters
        ----------
        values
            Values or expression to check for membership

        Returns
        -------
        BooleanValue
            Expression indicating membership

        Examples
        --------
        >>> import ibis
        >>> table = ibis.table([('string_col', 'string')])
        >>> table2 = ibis.table([('other_string_col', 'string')])
        >>> expr = table.string_col.isin(['foo', 'bar', 'baz'])
        >>> expr2 = table.string_col.isin(table2.other_string_col)
        """
        import ibis.expr.operations as ops

        return ops.Contains(self, values).to_expr()

    def notin(
        self,
        values: ValueExpr | Sequence[ValueExpr],
    ) -> ir.BooleanValue:
        """Check whether this expression's values are not in `values`.

        Parameters
        ----------
        values
            Values or expression to check for lack of membership

        Returns
        -------
        BooleanValue
            Whether `self`'s values are not contained in `values`
        """
        import ibis.expr.operations as ops

        return ops.NotContains(self, values).to_expr()

    def substitute(
        self,
        value: ValueExpr,
        replacement: ValueExpr | None = None,
        else_: ValueExpr | None = None,
    ):
        """Replace one or more values in a value expression.

        Parameters
        ----------
        value
            Expression or mapping
        replacement
            Expression. If an expression is passed to value, this must be
            passed.
        else_
            Expression

        Returns
        -------
        ValueExpr
            Replaced values
        """
        expr = self.case()
        if isinstance(value, dict):
            for k, v in sorted(value.items()):
                expr = expr.when(k, v)
        else:
            expr = expr.when(value, replacement)

        return expr.else_(else_ if else_ is not None else self).end()

    def over(self, window: win.Window) -> ValueExpr:
        """Construct a window expression.

        Parameters
        ----------
        window
            Window specification

        Returns
        -------
        ValueExpr
            A window function expression
        """
        import ibis.expr.operations as ops

        prior_op = self.op()

        if isinstance(prior_op, ops.WindowOp):
            op = prior_op.over(window)
        else:
            op = ops.WindowOp(self, window)

        result = op.to_expr()

        if self.has_name():
            return result.name(self.get_name())
        return result

    def isnull(self) -> ir.BooleanValue:
        """Return whether this expression is NULL."""
        import ibis.expr.operations as ops

        return ops.IsNull(self).to_expr()

    def notnull(self) -> ir.BooleanValue:
        """Return whether this expression is not NULL."""
        import ibis.expr.operations as ops

        return ops.NotNull(self).to_expr()

    def case(self):
        """Create a SimpleCaseBuilder to chain multiple if-else statements.

        Add new search expressions with the `.when()` method. These must be
        comparable with this column expression. Conclude by calling `.end()`

        Returns
        -------
        SimpleCaseBuilder
            A case builder

        Examples
        --------
        >>> import ibis
        >>> t = ibis.table([('string_col', 'string')], name='t')
        >>> expr = t.string_col
        >>> case_expr = (expr.case()
        ...              .when('a', 'an a')
        ...              .when('b', 'a b')
        ...              .else_('null or (not a and not b)')
        ...              .end())
        >>> case_expr
        r0 := UnboundTable[t]
          string_col string
        SimpleCase(base=r0.string_col, cases=[ValueList(values=['a', 'b'])], results=[ValueList(values=['an a', 'a b'])], default='null or (not a and not b)')
        """  # noqa: E501
        import ibis.expr.builders as bl

        return bl.SimpleCaseBuilder(self)

    def cases(
        self,
        case_result_pairs: Iterable[tuple[ir.BooleanValue, ValueExpr]],
        default: ValueExpr | None = None,
    ) -> ValueExpr:
        """Create a case expression in one shot.

        Parameters
        ----------
        case_result_pairs
            Conditional-result pairs
        default
            Value to return if none of the case conditions are true

        Returns
        -------
        ValueExpr
            Value expression
        """
        builder = self.case()
        for case, result in case_result_pairs:
            builder = builder.when(case, result)
        return builder.else_(default).end()

    def collect(self) -> ir.ArrayValue:
        """Return an array of the elements of this expression."""
        import ibis.expr.operations as ops

        return ops.ArrayCollect(self).to_expr()

    def identical_to(self, other: ValueExpr) -> ir.BooleanValue:
        """Return whether this expression is identical to other.

        Corresponds to `IS NOT DISTINCT FROM` in SQL.

        Parameters
        ----------
        other
            Expression to compare to

        Returns
        -------
        BooleanValue
            Whether this expression is not distinct from `other`
        """
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        try:
            return ops.IdenticalTo(self, rlz.any(other)).to_expr()
        except (com.IbisTypeError, NotImplementedError):
            return NotImplemented

    def group_concat(
        self,
        sep: str = ",",
        where: ir.BooleanValue | None = None,
    ) -> ir.StringScalar:
        """Concatenate values using the indicated separator to produce a string.

        Parameters
        ----------
        sep
            Separator will be used to join strings
        where
            Filter expression

        Returns
        -------
        StringScalar
            Concatenated string expression
        """
        import ibis.expr.operations as ops

        return ops.GroupConcat(self, sep=sep, where=where).to_expr()

    def __hash__(self) -> int:
        return hash((self._name, self._dtype, self._arg))

    def __eq__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.Equals, self, rlz.any(other))

    def __ne__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.NotEquals, self, rlz.any(other))

    def __ge__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.GreaterEqual, self, rlz.any(other))

    def __gt__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.Greater, self, rlz.any(other))

    def __le__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.LessEqual, self, rlz.any(other))

    def __lt__(self, other: AnyValue) -> ir.BooleanValue:
        import ibis.expr.operations as ops
        import ibis.expr.rules as rlz

        return _binop(ops.Less, self, rlz.any(other))


@public
class AnyScalar(ScalarExpr, AnyValue):
    pass  # noqa: E701,E302


@public
class AnyColumn(ColumnExpr, AnyValue):
    def bottomk(self, k: int, by: ValueExpr | None = None) -> ir.TopKExpr:
        raise NotImplementedError("bottomk is not implemented")

    def distinct(self) -> ColumnExpr:
        """Compute the set of unique values.

        Cannot be used in conjunction with other array expressions from the
        same context.

        Returns
        -------
        ColumnExpr
            Distinct values
        """
        import ibis.expr.operations as ops

        return ops.DistinctColumn(self).to_expr()

    def approx_nunique(
        self,
        where: ir.BooleanValue | None = None,
    ) -> ir.IntegerScalar:
        import ibis.expr.operations as ops

        return ops.HLLCardinality(self, where).to_expr().name("approx_nunique")

    def approx_median(
        self,
        where: ir.BooleanValue | None = None,
    ) -> ScalarExpr:
        import ibis.expr.operations as ops

        return ops.CMSMedian(self, where).to_expr().name("approx_median")

    def max(self, where: ir.BooleanValue | None = None) -> ScalarExpr:
        import ibis.expr.operations as ops

        return ops.Max(self, where).to_expr().name("max")

    def min(self, where: ir.BooleanValue | None = None) -> ScalarExpr:
        import ibis.expr.operations as ops

        return ops.Min(self, where).to_expr().name("min")

    def nunique(
        self, where: ir.BooleanValue | None = None
    ) -> ir.IntegerScalar:
        import ibis.expr.operations as ops

        return ops.CountDistinct(self, where).to_expr().name("nunique")

    def topk(
        self,
        k: int,
        by: ir.ValueExpr | None = None,
    ) -> ir.TopKExpr:
        """Return a "top k" expression.

        Parameters
        ----------
        k
            Return this number of rows
        by
            An expression. Defaults to the count

        Returns
        -------
        TopKExpr
            A top-k expression
        """
        import ibis.expr.operations as ops

        op = ops.TopK(self, k, by=by if by is not None else self.count())
        return op.to_expr()

    def summary(
        self,
        exact_nunique: bool = False,
        prefix: str = "",
        suffix: str = "",
    ) -> list[ir.NumericScalar]:
        """Compute a set of summary metrics.

        Parameters
        ----------
        exact_nunique
            Compute the exact number of distinct values. Typically slower if
            `True`.
        prefix
            String prefix for metric names
        suffix
            String suffix for metric names

        Returns
        -------
        list[NumericScalar]
            Metrics list
        """
        if exact_nunique:
            unique_metric = self.nunique().name('uniques')
        else:
            unique_metric = self.approx_nunique().name('uniques')

        metrics = [
            self.count(),
            self.isnull().sum().name('nulls'),
            unique_metric,
        ]
        metrics = [m.name(f"{prefix}{m.get_name()}{suffix}") for m in metrics]

        return metrics

    def arbitrary(
        self,
        where: ir.BooleanValue | None = None,
        how: str | None = None,
    ) -> ScalarExpr:
        """Select an arbitrary value in a column.

        Parameters
        ----------
        where
            A filter expression
        how
            Heavy selects a frequently occurring value using the heavy hitters
            algorithm. Heavy is only supported by Clickhouse backend.

        Returns
        -------
        ScalarExpr
            An expression
        """
        import ibis.expr.operations as ops

        return ops.Arbitrary(self, how=how, where=where).to_expr()

    def count(self, where: ir.BooleanValue | None = None) -> ir.IntegerScalar:
        """Compute the number of rows in an expression.

        Parameters
        ----------
        where
            Filter expression

        Returns
        -------
        IntegerScalar
            Number of elements in an expression
        """
        import ibis.expr.operations as ops

        op = self.op()
        if isinstance(op, ops.DistinctColumn):
            result = ops.CountDistinct(op.args[0], where).to_expr()
        else:
            result = ops.Count(self, where).to_expr()

        return result.name("count")

    def value_counts(self, metric_name: str = "count") -> ir.TableExpr:
        """Compute a frequency table.

        Returns
        -------
        TableExpr
            Frequency table expression
        """
        from .relations import find_base_table

        base = find_base_table(self)
        metric = base.count().name(metric_name)

        if not self.has_name():
            expr = self.name("unnamed")
        else:
            expr = self

        return base.group_by(expr).aggregate(metric)

    def first(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.FirstValue(self).to_expr()

    def last(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.LastValue(self).to_expr()

    def rank(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.MinRank(self).to_expr()

    def dense_rank(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.DenseRank(self).to_expr()

    def percent_rank(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.PercentRank(self).to_expr()

    def cummin(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.CumulativeMin(self).to_expr()

    def cummax(self) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.CumulativeMax(self).to_expr()

    def lag(
        self,
        offset: int | ir.IntegerValue | None = None,
        default: ValueExpr | None = None,
    ) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.Lag(self, offset, default).to_expr()

    def lead(
        self,
        offset: int | ir.IntegerValue | None = None,
        default: ValueExpr | None = None,
    ) -> ColumnExpr:
        import ibis.expr.operations as ops

        return ops.Lead(self, offset, default).to_expr()

    def ntile(self, buckets: int | ir.IntegerValue) -> ir.IntegerColumn:
        import ibis.expr.operations as ops

        return ops.NTile(self, buckets).to_expr()

    def nth(self, n: int | ir.IntegerValue) -> ColumnExpr:
        """Return the `n`th value over a window.

        Parameters
        ----------
        n
            Desired rank value

        Returns
        -------
        ColumnExpr
            The nth value over a window
        """
        import ibis.expr.operations as ops

        return ops.NthValue(self, n).to_expr()


@public
class NullValue(AnyValue):
    pass  # noqa: E701,E302


@public
class NullScalar(AnyScalar, NullValue):
    pass  # noqa: E701,E302


@public
class NullColumn(AnyColumn, NullValue):
    pass  # noqa: E701,E302


@public
class ListExpr(ColumnExpr, AnyValue):
    @property
    def values(self):
        return self.op().values

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, key):
        return self.values[key]

    def __add__(self, other):
        other_values = tuple(getattr(other, 'values', other))
        return type(self.op())(self.values + other_values).to_expr()

    def __radd__(self, other):
        other_values = tuple(getattr(other, 'values', other))
        return type(self.op())(other_values + self.values).to_expr()

    def __bool__(self):
        return bool(self.values)

    __nonzero__ = __bool__

    def __len__(self):
        return len(self.values)


_NULL = None


@public
def null():
    """Create a NULL/NA scalar"""
    import ibis.expr.operations as ops

    global _NULL
    if _NULL is None:
        _NULL = ops.NullLiteral().to_expr()

    return _NULL


@public
def literal(value: Any, type: dt.DataType | str | None = None) -> ScalarExpr:
    """Create a scalar expression from a Python value.

    !!! tip "Use specific functions for arrays, structs and maps"

        Ibis supports literal construction of arrays using the following
        functions:

        1. [`ibis.array`][ibis.array]
        1. [`ibis.struct`][ibis.struct]
        1. [`ibis.map`][ibis.map]

        Constructing these types using `literal` will be deprecated in a future
        release.

    Parameters
    ----------
    value
        A Python value
    type
        An instance of [`DataType`][ibis.expr.datatypes.DataType] or a string
        indicating the ibis type of `value`. This parameter can be used
        in cases where ibis's type inference isn't sufficient for discovering
        the type of `value`.

    Returns
    -------
    ScalarExpr
        An expression representing a literal value

    Examples
    --------
    Construct an integer literal

    >>> import ibis
    >>> x = ibis.literal(42)
    >>> x.type()
    Int8(nullable=True)

    Construct a `float64` literal from an `int`

    >>> y = ibis.literal(42, type='double')
    >>> y.type()
    Float64(nullable=True)

    Ibis checks for invalid types

    >>> ibis.literal('foobar', type='int64')  # doctest: +ELLIPSIS
    Traceback (most recent call last):
      ...
    TypeError: Value 'foobar' cannot be safely coerced to int64
    """
    import ibis.expr.datatypes as dt
    import ibis.expr.operations as ops

    if hasattr(value, 'op') and isinstance(value.op(), ops.Literal):
        return value

    try:
        inferred_dtype = dt.infer(value)
    except com.InputTypeError:
        has_inferred = False
    else:
        has_inferred = True

    if type is None:
        has_explicit = False
    else:
        has_explicit = True
        explicit_dtype = dt.dtype(type)

    if has_explicit and has_inferred:
        try:
            # ensure type correctness: check that the inferred dtype is
            # implicitly castable to the explicitly given dtype and value
            dtype = inferred_dtype.cast(explicit_dtype, value=value)
        except com.IbisTypeError:
            raise TypeError(
                f'Value {value!r} cannot be safely coerced to {type}'
            )
    elif has_explicit:
        dtype = explicit_dtype
    elif has_inferred:
        dtype = inferred_dtype
    else:
        raise TypeError(
            'The datatype of value {!r} cannot be inferred, try '
            'passing it explicitly with the `type` keyword.'.format(value)
        )

    if dtype is dt.null:
        return null().cast(dtype)
    else:
        value = dt._normalize(dtype, value)
        return ops.Literal(value, dtype=dtype).to_expr()
